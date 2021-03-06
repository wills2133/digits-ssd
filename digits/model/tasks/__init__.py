# Copyright (c) 2014-2017, NVIDIA CORPORATION.  All rights reserved.
from __future__ import absolute_import

from .caffe_train import CaffeTrainTask
##########################################
from .distrib_caffe_train import DistributedTrainTask
##########################################
from .torch_train import TorchTrainTask
from .train import TrainTask
import ssd_pascal

__all__ = [
    'CaffeTrainTask',
    'DistributedTrainTask', ##########
    'TorchTrainTask',
    'TrainTask',
]

from digits.config import config_value  # noqa

if config_value('tensorflow')['enabled']:
    from .tensorflow_train import TensorflowTrainTask  # noqa
    __all__.append('TensorflowTrainTask')
