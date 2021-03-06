###derived by wills
from __future__ import absolute_import

from collections import OrderedDict
import copy
import math
import operator
import os
import re
import sys
import time

from google.protobuf import text_format
import numpy as np
import platform
import scipy

from .caffe_train import CaffeTrainTask
import digits
from digits import utils
from digits.config import config_value
from digits.status import Status
from digits.utils import subclass, override, constants
from digits.utils.filesystem import tail

import werkzeug.exceptions

# Must import after importing digit.config
import caffe
import caffe_pb2


# NOTE: Increment this every time the pickled object changes
PICKLE_VERSION = 5

# Constants
CAFFE_SOLVER_FILE = 'solver.prototxt'
CAFFE_ORIGINAL_FILE = 'original.prototxt'
CAFFE_TRAIN_VAL_FILE = 'train_val.prototxt'
CAFFE_SNAPSHOT_PREFIX = 'snapshot'
CAFFE_DEPLOY_FILE = 'deploy.prototxt'
CAFFE_PYTHON_LAYER_FILE = 'digits_python_layers.py'

@subclass
class DistributedTrainTask(CaffeTrainTask):
    """
    Trains a caffe in other servers
    """

    def __init__(self, **kwargs):
        """
        Arguments:
        network -- a caffe NetParameter defining the network
        """
        ###############
        self.max_iter_num = kwargs.pop('max_iter_num', None)
        self.data_dir = kwargs.pop('data_dir', None)
        self.test_batch_size = kwargs.pop('test_batch_size', None)
        self.network_type=kwargs.pop('network_type', None)
        self.network_text = kwargs.pop('network_text', None)
        self.train_server_ip = kwargs.pop('train_server_ip', None)
        self.train_server_port = kwargs.pop('train_server_port', None)
        ###############
        super(DistributedTrainTask, self).__init__(**kwargs)

    def save_files_generic(self):
        #####
        from digits.job_client import ssd_pascal
        ############## parameters #############
        # Add non-data layers
        job_path = self.path(self.train_val_file)
        solver_file = self.path('solver.prototxt')
        train_net_path = self.path('train_val.prototxt')
        test_net_path = self.path('test.prototxt')
        snapshot_path = self.path('VOC_Snapshot')
        train_data_path = self.data_dir+'/'+'VOC0712_trainval_lmdb'
        test_data_path = self.data_dir+'/'+'VOC0712_test_lmdb'
        label_map_file = self.data_dir+'/'+'labelmap_voc.prototxt'
        name_size_file = self.data_dir+'/'+'test_name_size.txt'
        output_result_dir = self.data_dir+'/'+'Main'

        iter_size = self.batch_accumulation / self.batch_size
        ################ end ##################
        print '----------------------------------------------'
        print 'train_ssd'
        print '----------------------------------------------'
        ############## train_net ##############
        # ssd_pascal.CreateTrainNet(train_net_path, train_data_path, self.batch_size) 
        ###directly edit on custom network text form page
        network_test, n = re.subn('(?<=source:)(.+)?(?=\n)', '"'+train_data_path+'"', self.network_text)
        # print (network_test)
        f = open(train_net_path, 'w')
        f.write(network_test)
        f.close()
        ################ end ##################

        ############### test_net ############## 
        # print 'create test.prototxt'
        # ssd_pascal.CreateTestNet(test_net_path, test_data_path, self.test_batch_size, 
        #     label_map_file, name_size_file, output_result_dir)
        ################# end #################
                                 
        ############## ssd solver #############
        solver = caffe_pb2.SolverParameter()

        # solver.max_iter = 120000
        solver.max_iter = self.max_iter_num
        self.solver = solver

        # Create solver
        ssd_pascal.CreateSolver(solver_file, 
            train_net_path, test_net_path, snapshot_path, 
            self.learning_rate, iter_size, self.solver_type)
        ################### end ###############

        ############## deploy_net #############
        deploy_network = caffe_pb2.NetParameter()
        # Write to file
        with open(self.path(self.deploy_file), 'w') as outfile:
            text_format.PrintMessage(deploy_network, outfile)

        with open(self.path('original.prototxt'), 'w') as outfile:
            text_format.PrintMessage(deploy_network, outfile)

        ################# end #################

        ############## snapshot ##############

        solver.snapshot_prefix = self.snapshot_prefix

        snapshot_interval = self.snapshot_interval * ( solver.max_iter / self.train_epochs )
        if 0 < snapshot_interval <= 1:
            solver.snapshot = 1  # don't round down
        elif 1 < snapshot_interval < solver.max_iter:
            solver.snapshot = int(snapshot_interval)
        else:
            solver.snapshot = 0  # only take one snapshot at the end

        ################# end #################
        
        return True

    def run(self, resources):

        from digits.job_client import job_client
        """
        Execute the task

        Arguments:
        resources -- the resources assigned by the scheduler for this task
        """
        self.before_run()

        env = os.environ.copy()
        args = self.task_arguments(resources, env)
        if not args:
            self.logger.error('Could not create the arguments for Popen')
            self.status = Status.ERROR
            return False
        # Convert them all to strings
        args = [str(x) for x in args]

        self.logger.info('%s task started.' % self.name())
        self.status = Status.RUN
        unrecognized_output = []

        import sys
        env['PYTHONPATH'] = os.pathsep.join(['.', self.job_dir, env.get('PYTHONPATH', '')] + sys.path)

        # https://docs.python.org/2/library/subprocess.html#converting-argument-sequence
        if platform.system() == 'Windows':
            args = ' '.join(args)
            self.logger.info('Task subprocess args: "{}"'.format(args))
        else:
            self.logger.info('Task subprocess args: "%s"' % ' '.join(args))

        job_server_ip = str(self.train_server_ip)
        job_server_host = int(self.train_server_port)
        job_server_addr = (job_server_ip, job_server_host)

        sigterm_time = None  # When was the SIGTERM signal sent
        sigterm_timeout = 2  # When should the SIGKILL signal be sent

        socket_time = time.time()  #rescord last time get socket message
        socket_timeout = 600

        # save dataset server info
        try:
            f_info_r = open(self.data_dir+'/server_job_info.txt', 'r')
            server_info = f_info_r.readlines()
            f_info_w = open(self.job_dir+'/server_job_info.txt', 'w')
            f_info_w.writelines(server_info)
            f_info_w.write(self.train_server_ip + '\n')
            f_info_w.write(self.train_server_port + '\n')
            f_info_r.close()
            f_info_w.close()
        except Exception:
            print 'error when creating' + self.job_dir + '/server_job_info.txt'
            raise


        thread_log = job_client.training_request( job_server_addr, self.job_id, (' ').join(args) , self.job_dir, self.network_type)
        try:
            n = 0
            if not os.path.exists(self.job_dir):
                os.mkdir(self.job_dir)
            f = open(self.job_dir+'/log.txt', 'w') #save log file

            while ( not thread_log.stopped ) or ( n < len( thread_log.log_list ) ):
                # print '**************************************************'
                # print '--------------------------------------------------'
                print 'digits is waiting for response...'

                if self.aborted.is_set():
                    if sigterm_time is None:
                        # Attempt graceful shutdown
                        job_client.abort_request( job_server_addr, self.job_id )
                        thread_log.stop()
                        sigterm_time = time.time()
                        self.status = Status.ABORT
                        # break

                while n < len( thread_log.log_list ):
                    line = thread_log.log_list[n]
                    # print 'n', n
                    # print 'len( thread_log.log_list', len( thread_log.log_list )
                    # print 'line', line
                    if line:
                        f.write(line)
                        socket_time = time.time()
                        # print line
                        if not self.process_output(line):
                            self.logger.warning('%s unrecognized output: %s' % (self.name(), line.strip()))
                            unrecognized_output.append(line)
                    else:
                        time.sleep(0.05)
                    n += 1


                if sigterm_time is not None and (time.time() - sigterm_time > sigterm_timeout):
                    self.logger.warning('Fail to abort normally, Sent SIGKILL to task "%s"' % self.name())
                    job_client.abort_request( job_server_addr, self.job_id )
                    thread_log.stop()
                    # self.logger.warning('Sent SIGKILL to task "%s"' % self.name())
                    time.sleep(0.1)
                    break

                # print 'interval', (time.time() - socket_time)
                # if (time.time() - socket_time > socket_timeout):
                #     raise werkzeug.exceptions.Forbidden('get no response form server, abort job')
                    
                time.sleep(0.5)
            f.close()
        except Exception as RUN_ERROR:
            print 'interupt while training!'
            job_client.abort_request( job_server_addr, self.job_id )
            thread_log.stop()
            self.after_run()
            self.status = Status.ERROR
            time.sleep(0.1)
            raise RUN_ERROR
        
        self.after_run()

        if self.status != Status.RUN:
            return False
        else:
            self.logger.info('%s task completed.' % self.name())
            self.status = Status.DONE
            return True

    @override
    def process_output(self, line):
        
        float_exp = '(-NaN|NaN|[-+]?[0-9]*\.?[0-9]+(e[-+]?[0-9]+)?)'

        self.caffe_log.write('%s\n' % line)

        self.caffe_log.flush()
        # parse caffe output
        # print '-----line', line
        timestamp, level, message = self.preprocess_output_caffe(line)
        if not message:
            return True
        
        # iteration updates
        match = re.match(r'Iteration (\d+)', message)
        if match:
            
            i = int(match.group(1))
            self.new_iteration(i)

        # net output
        # match = re.match(r'(Train|Test) net output #(\d+): (\S*) = %s' % float_exp, message, flags=re.IGNORECASE)
        match = re.match( r'Iteration (\d+), (\S*) = %s' % float_exp, message, flags = re.IGNORECASE )

        if match:

            phase = int(match.group(1))
            name = match.group(2)
            value = match.group(3)
            ########################
            #-nan
            # print '-----message = ', message
            # print '-----phase = ', phase
            # print '-----name = ', name
            # print '-----value = ', value
            if value.lower() == 'nan':
                value = 0
            # assert value.lower() != 'nan', \
            #     'Network outputted %s for "%s" (%s phase). Try decreasing your learning rate.' % (value, name, phase)
            ########################
            value = float(value)
            # Find the layer type
            kind = '?'
            for layer in self.network.layer:
                if name in layer.top:
                    kind = layer.type
                    break

            self.save_train_output(name, kind, value)
            # if phase.lower() == 'train':
            #     self.save_train_output(name, kind, value)
            # elif phase.lower() == 'test':
            #     self.save_val_output(name, kind, value)
            # return True
        # else:
        #     print 'Iteration message no match'

        # # learning rate updates
        # match = re.match(r'Iteration (\d+).*lr = %s' % float_exp, message, flags=re.IGNORECASE)
        # if match:
        #     i = int(match.group(1))
        #     lr = float(match.group(2))
        #     self.save_train_output('learning_rate', 'LearningRate', lr)
        #     return True



        # snapshot starting # snapshot saved
        match = re.search(r'model_iter_(\d*)', message)
        if match:
            iter_num = match.group(1)
            with open(self.job_dir+'/model_list.txt', 'a+') as f:
                f.write('model_iter_{}\n'.format(iter_num))

            self.logger.debug('Snapshot saved.')

            self.detect_snapshots()

            # self.snapshots.append( ['model_iter_{}'.format(iter_num), str(iter_num)] )
            self.send_snapshot_update()
            self.saving_snapshot = False
            return True
        # else:
        #     print 'model creating message no match'
        # if level in ['error', 'critical']:
        #     self.logger.error('%s: %s' % (self.name(), message))
        #     self.exception = message
        #     return True

        return True

    def preprocess_output_caffe(self, line):
        """
        Takes line of output and parses it according to caffe's output format
        Returns (timestamp, level, message) or (None, None, None)
        """
        # NOTE: This must change when the logging format changes
        # LMMDD HH:MM:SS.MICROS pid file:lineno] message
        # match = re.match(r'(\w)(\d{4} \S{8}).*]\s+(\S.*)$', line)
        match = re.search(r'(\w)(\d* \S*)] (.*)$', line)
        if match:
            level = match.group(1)
            # add the year because caffe omits it
            # timestr = '%s%s' % (time.strftime('%Y'), match.group(2))
            message = match.group(3)
            if level == 'I':
                level = 'info'
            elif level == 'W':
                level = 'warning'
            elif level == 'E':
                level = 'error'
            elif level == 'F':  # FAIL
                level = 'critical'
            # timestamp = time.mktime(time.strptime(timestr, '%Y%m%d %H:%M:%S'))
            timestamp = time.mktime(time.strptime(time.strftime('%Y%m%d %H:%M:%S'), '%Y%m%d %H:%M:%S'))
            return (timestamp, level, message)
        else:
            # print 'symbol message not match'
            return (None, None, None)

    def send_snapshot_update(self):
        """
        Sends socketio message about the snapshot list
        """
        from digits.webapp import socketio

        socketio.emit('task update',
                      {
                          'task': self.html_id(),
                          'update': 'snapshots',
                          'data': self.snapshot_list(),
                      },
                      namespace='/jobs',
                      room=self.job_id,
                      )

    @override
    def detect_snapshots(self):
        self.snapshots = []

        model_list_path = self.job_dir+'/model_list.txt'
        snapshots = []
        # find models
        if os.path.exists(model_list_path):
            with open(model_list_path, 'r') as f:
                model_list = f.readlines()
            for model in model_list:
                iter_num = int( model.split('_')[2] )
                snapshots.append((
                    'model_iter_{}'.format(iter_num),
                    iter_num
                ))

        # else:
        #     print 'model_list_path not found'

        # delete all but the most recent solverstate
        # for filename, iteration in sorted(solverstates, key=lambda tup: tup[1])[:-1]:
        #     # print 'Removing "%s"' % filename
        #     os.remove(filename)

        self.snapshots = sorted(snapshots, key=lambda tup: tup[1])

        return len(self.snapshots) > 0

    def snapshot_list(self):
        """
        Returns an array of arrays for creating an HTML select field
        """
        return [[s[1], 'model_iter_%s' % s[1]] for s in reversed(self.snapshots)]