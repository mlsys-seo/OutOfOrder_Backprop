import os
import sys
import time
import numpy as np
import tensorflow as tf
from tensorflow.python.training import training_ops

import densenet_schedule_map
import encode

tf.compat.v1.disable_eager_execution()

BATCH = int(sys.argv[1])
GROWTH_K = int(sys.argv[2])


def conv2d(x, filter, kernel, stride=1, name="CONV"):
    return tf.compat.v1.layers.conv2d(
        inputs=x,
        filters=filter,
        kernel_size=kernel,
        strides=stride,
        use_bias=False,
        padding="SAME",
        name=name,
        data_format="channels_first",
    )


def batch_normalization(x):
    return tf.compat.v1.layers.batch_normalization(inputs=x, axis=1)


def relu(x):
    return tf.nn.relu(x)


def max_pooling(x, pool_size=[3, 3], stride=2, padding="VALID"):
    return tf.compat.v1.layers.max_pooling2d(
        inputs=x,
        pool_size=pool_size,
        strides=stride,
        padding=padding,
        data_format="channels_first",
    )


def concat(xs):
    return tf.concat(xs, axis=1)


def linear(x):
    return tf.compat.v1.layers.dense(inputs=x, units=1000)


class DenseNet:
    def __init__(self, x, growth_k=32, depth=121):
        assert depth == 121 or depth == 169 or depth == 201 or depth == 264

        self._curr_layer_num = 0
        self._growth_k = growth_k

        if depth == 121:
            num_layers_per_block = [6, 12, 24, 16]
        elif depth == 169:
            num_layers_per_block = [6, 12, 32, 32]
        elif depth == 201:
            num_layers_per_block = [6, 12, 48, 32]
        elif depth == 264:
            num_layers_per_block = [6, 12, 64, 48]

        self.model = self._make_model(x, num_layers_per_block)

    def _conv_layer(self, x, filter, kernel, stride=1):
        layer_name = "_".join(["CONV", str(self._curr_layer_num)])
        conv = conv2d(
            x,
            filter,
            kernel,
            stride,
            name=encode.encode_sched_map_into_name(
                layer_name,
                self._curr_layer_num,
                densenet_schedule_map.weight_gradient_schedule_map,
            ),
        )
        self._curr_layer_num += 1

        return conv

    def _transition_layer(self, x):
        x = batch_normalization(x)
        x = relu(x)

        in_channel = x.shape[1] // 2
        x = self._conv_layer(x, filter=int(in_channel), kernel=[1, 1])
        x = relu(x)
        x = max_pooling(x, pool_size=[2, 2], stride=2, padding="SAME")

        return x

    def _bottleneck_layer(self, x):
        x = batch_normalization(x)
        x = self._conv_layer(x, filter=4 * self._growth_k, kernel=[1, 1])
        x = relu(x)

        x = batch_normalization(x)
        x = self._conv_layer(x, filter=self._growth_k, kernel=[3, 3])
        x = relu(x)

        return x

    def _dense_block(self, x, num_layers):
        layer_outputs = [x]

        x = self._bottleneck_layer(x)
        layer_outputs.append(x)

        for i in range(num_layers - 1):
            x = concat(layer_outputs)
            x = self._bottleneck_layer(x)
            layer_outputs.append(x)

        return concat(layer_outputs)

    def _make_model(self, x, num_layers_per_block):
        with tf.compat.v1.name_scope("INIT"):
            x = self._conv_layer(x, filter=2 * self._growth_k, kernel=[7, 7], stride=2)
            x = relu(x)
            x = max_pooling(x, pool_size=[3, 3], stride=2, padding="SAME")

        with tf.compat.v1.name_scope("B1"):
            x = self._dense_block(x, num_layers_per_block[0])
            x = self._transition_layer(x)

        with tf.compat.v1.name_scope("B2"):
            x = self._dense_block(x, num_layers_per_block[1])
            x = self._transition_layer(x)

        with tf.compat.v1.name_scope("B3"):
            x = self._dense_block(x, num_layers_per_block[2])
            x = self._transition_layer(x)

        with tf.compat.v1.name_scope("B4"):
            x = self._dense_block(x, num_layers_per_block[3])

        x = relu(x)
        x = max_pooling(x)
        x = tf.compat.v1.layers.flatten(x)
        x = linear(x)

        return x


def main():
    num_classes = 1000

    dummy_X = tf.stop_gradient(
        tf.Variable(
            tf.random.normal([BATCH, 3, 224, 224]), name="input_data", dtype="float"
        )
    )
    dummy_Y = tf.random.uniform(
        [BATCH], minval=0, maxval=num_classes - 1, dtype=tf.int32, name="label_data"
    )

    logits = DenseNet(x=dummy_X, growth_k=GROWTH_K, depth=121).model
    optimizer = tf.compat.v1.train.GradientDescentOptimizer(learning_rate=0.1)

    cost = tf.reduce_mean(
        input_tensor=tf.nn.sparse_softmax_cross_entropy_with_logits(
            labels=dummy_Y, logits=logits
        )
    )
    gvs = optimizer.compute_gradients(cost, tf.compat.v1.trainable_variables())
    train_op = optimizer.apply_gradients(gvs)

    config = tf.compat.v1.ConfigProto()
    config.gpu_options.allow_growth = True
    with tf.compat.v1.Session(config=config) as sess:
        sess.run(tf.compat.v1.global_variables_initializer())

        ################################################
        # Running MobileNet v3 with Tensorflow XLA  
        ################################################
        warmup_step = 3
        tf_graph_step = 50 + warmup_step
        oneiter_times = []
        print("========== XLA Training Start ==========")
        for step in range(tf_graph_step):
            start_time = time.time()
            sess.run([train_op])
            end_time = time.time()

            oneiter_time = end_time - start_time
            oneiter_times.append(oneiter_time)
        print("=========== XLA Training End ===========")

        # The execution time of the first few iteration is high because of TF graph initialization and GPU initialization overhead.
        # So it disturbs to measure the average execution time.
        oneiter_times.sort()
        for _ in range(warmup_step):
            oneiter_times.pop()

        avg_time = sum(oneiter_times) / len(oneiter_times)
        print("XLA Training Throughput : {:.2f} (images/sec)".format(BATCH / avg_time))


if __name__ == "__main__":
    main()

