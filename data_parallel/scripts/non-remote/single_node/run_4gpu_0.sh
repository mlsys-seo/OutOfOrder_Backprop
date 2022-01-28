#!/bin/bash

export MODEL_SIZE=50
export BATCH_SIZE=5

export REVERSE_FIRST_K=$1

export MASTER_HOST=127.0.0.1
export MASTER_PORT=1234
export NODE_HOST=127.0.0.1
export NUM_WORKER=4
export NUM_SERVER=1
export NUM_SERVER_PER_NODE=1

export INDEX=0
export GPU_IDX=0
export DEBUG_PRINT=0

ROOT_DIR=$(dirname $(dirname $(dirname $(realpath $0))))

$ROOT_DIR/examples/run_node_resnet.sh \
		$MODEL_SIZE $BATCH_SIZE $NUM_TRAINING_STEP $REVERSE_FIRST_K $MASTER_HOST $MASTER_PORT $NODE_HOST $NUM_WORKER $NUM_SERVER $NUM_SERVER_PER_NODE $INDEX $GPU_IDX $DEBUG_PRINT 