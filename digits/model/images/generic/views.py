#!/usr/bin/env python
# coding=utf-8

# Copyright (c) 2015-2017, NVIDIA CORPORATION.  All rights reserved.
from __future__ import absolute_import

import os
import re
import tempfile

import flask
import werkzeug.exceptions

from .forms import GenericImageModelForm
from .job import GenericImageModelJob
from digits.pretrained_model.job import PretrainedModelJob
from digits import extensions, frameworks, utils
from digits.config import config_value
from digits.dataset import GenericDatasetJob, GenericImageDatasetJob
from digits.inference import ImageInferenceJob
from digits.status import Status
from digits.utils import filesystem as fs
from digits.utils import constants
from digits.utils.forms import fill_form_if_cloned, save_form_to_job
from digits.utils.routing import request_wants_json, job_from_request
from digits.webapp import scheduler

from flask import redirect

blueprint = flask.Blueprint(__name__, __name__)
#######################################################
from digits.frameworks import Framework
from digits.utils import subclass, override, parse_version

class framenet(Framework):

    """
    Defines required methods to interact with the Caffe framework
    This class can be instantiated as many times as there are compatible
    instances of Caffe
    """

    # short descriptive name

    # identifier of framework class (intended to be the same across
    # all instances of this class)
    CLASS = 'caffe'

    # whether this framework can shuffle data during training
    CAN_SHUFFLE_DATA = False
    SUPPORTS_PYTHON_LAYERS_FILE = True
    SUPPORTS_TIMELINE_TRACING = False

    if config_value('caffe')['flavor'] == 'NVIDIA':
        if parse_version(config_value('caffe')['version']) > parse_version('0.14.0-alpha'):
            SUPPORTED_SOLVER_TYPES = ['SGD', 'NESTEROV', 'ADAGRAD',
                                      'RMSPROP', 'ADADELTA', 'ADAM']
        else:
            SUPPORTED_SOLVER_TYPES = ['SGD', 'NESTEROV', 'ADAGRAD']
    elif config_value('caffe')['flavor'] == 'BVLC':
        SUPPORTED_SOLVER_TYPES = ['SGD', 'NESTEROV', 'ADAGRAD',
                                  'RMSPROP', 'ADADELTA', 'ADAM']
    else:
        raise ValueError('Unknown flavor.  Support NVIDIA and BVLC flavors only.')

    SUPPORTED_DATA_TRANSFORMATION_TYPES = ['MEAN_SUBTRACTION', 'CROPPING']
    SUPPORTED_DATA_AUGMENTATION_TYPES = []

    @override
    def __init__(self, name):
        super(framenet, self).__init__()
        self.framework_id = name
        self.NAME = name

    @override
    def create_train_task(self, **kwargs):
        """
        create train task
        """
        return CaffeTrainTask(framework_id=self.framework_id, **kwargs)

    @override
    def validate_network(self, data):
        """
        validate a network (input data are expected to be a text
        description of the network)
        """
        pb = caffe_pb2.NetParameter()
        try:
            text_format.Merge(data, pb)
        except text_format.ParseError as e:
            raise BadNetworkError('Not a valid NetParameter: %s' % e)

    @override
    def get_standard_network_desc(self, network):
        """
        return description of standard network
        network is expected to be a instance of caffe_pb2.NetParameter
        """
        networks_dir = os.path.join(os.path.dirname(digits.__file__), 'standard-networks', self.CLASS)

        for filename in os.listdir(networks_dir):
            path = os.path.join(networks_dir, filename)
            if os.path.isfile(path):
                match = None
                match = re.match(r'%s.prototxt' % network, filename)
                if match:
                    with open(path) as infile:
                        return infile.read()
        # return None if not found
        return None

    @override
    def get_network_from_desc(self, network_desc):
        """
        return network object from a string representation
        """
        network = caffe_pb2.NetParameter()
        text_format.Merge(network_desc, network)
        return network

    @override
    def get_network_from_previous(self, previous_network, use_same_dataset):
        """
        return new instance of network from previous network
        """
        network = caffe_pb2.NetParameter()
        network.CopyFrom(previous_network)

        if not use_same_dataset:
            # Rename the final layer
            # XXX making some assumptions about network architecture here
            ip_layers = [l for l in network.layer if l.type == 'InnerProduct']
            if len(ip_layers) > 0:
                ip_layers[-1].name = '%s_retrain' % ip_layers[-1].name

        return network

    @override
    def get_network_from_path(self, path):
        """
        return network object from a file path
        """
        network = caffe_pb2.NetParameter()

        with open(path) as infile:
            text_format.Merge(infile.read(), network)

        return network

    @override
    def get_network_visualization(self, **kwargs):
        """
        return visualization of network
        """
        desc = kwargs['desc']
        net = caffe_pb2.NetParameter()
        text_format.Merge(desc, net)
        # Throws an error if name is None
        if not net.name:
            net.name = 'Network'
        return ('<image src="data:image/png;base64,' +
                caffe.draw.draw_net(net, 'UD').encode('base64') +
                '" style="max-width:100%" />')

    @override
    def can_accumulate_gradients(self):
        if config_value('caffe')['flavor'] == 'BVLC':
            return True
        elif config_value('caffe')['flavor'] == 'NVIDIA':
            return (parse_version(config_value('caffe')['version']) > parse_version('0.14.0-alpha'))
        else:
            raise ValueError('Unknown flavor.  Support NVIDIA and BVLC flavors only.')

############################################

@blueprint.route('/new', methods=['GET'])
@blueprint.route('/new/<extension_id>', methods=['GET'])
@utils.auth.requires_login
def new(extension_id=None):
    """
    Return a form for a new GenericImageModelJob
    """
    form = GenericImageModelForm()
    form.dataset.choices = get_datasets(extension_id)
    # form.standard_networks.choices = []
    #####################################
    form.standard_networks.choices = get_standard_networks()
    form.standard_networks.default = get_default_standard_network()
    #####################################
    form.previous_networks.choices = get_previous_networks()
    form.pretrained_networks.choices = get_pretrained_networks()
    prev_network_snapshots = get_previous_network_snapshots()

    # Is there a request to clone a job with ?clone=<job_id>
    fill_form_if_cloned(form)

    frameworks1 = [framenet('test'), framenet('train')]
    return flask.render_template(
        'models/images/generic/new.html',
        extension_id=extension_id,
        extension_title=extensions.data.get_extension(extension_id).get_title() if extension_id else None,
        form=form,
        frameworks=frameworks.get_frameworks(),
        # frameworks=frameworks1,
        previous_network_snapshots=prev_network_snapshots,
        previous_networks_fullinfo=get_previous_networks_fulldetails(),
        pretrained_networks_fullinfo=get_pretrained_networks_fulldetails(),
        multi_gpu=config_value('caffe')['multi_gpu'],
    )


@blueprint.route('<extension_id>.json', methods=['POST'])
@blueprint.route('<extension_id>', methods=['POST'], strict_slashes=False)
@blueprint.route('.json', methods=['POST'])
@blueprint.route('', methods=['POST'], strict_slashes=False)
@utils.auth.requires_login(redirect=False)
def create(extension_id=None):
    # raw_input("pause_generic")
    """
    Create a new GenericImageModelJob

    Returns JSON when requested: {job_id,name,status} or {errors:[]}
    """
    form = GenericImageModelForm()
    form.dataset.choices = get_datasets(extension_id)
    # form.standard_networks.choices = []
    #####################################
    form.standard_networks.choices = get_standard_networks()
    form.standard_networks.default = get_default_standard_network()
    #####################################
    form.previous_networks.choices = get_previous_networks()
    form.pretrained_networks.choices = get_pretrained_networks()
    prev_network_snapshots = get_previous_network_snapshots()

    # Is there a request to clone a job with ?clone=<job_id>
    fill_form_if_cloned(form)
    
    if not form.validate_on_submit():
        if request_wants_json():
            return flask.jsonify({'errors': form.errors}), 400
        else:
            return flask.render_template(
                'models/images/generic/new.html',
                extension_id=extension_id,
                extension_title=extensions.data.get_extension(extension_id).get_title() if extension_id else None,
                form=form,
                frameworks=frameworks.get_frameworks(),
                previous_network_snapshots=prev_network_snapshots,
                previous_networks_fullinfo=get_previous_networks_fulldetails(),
                pretrained_networks_fullinfo=get_pretrained_networks_fulldetails(),
                multi_gpu=config_value('caffe')['multi_gpu'],
            ), 400

    datasetJob = scheduler.get_job(form.dataset.data)

    if not datasetJob:
        raise werkzeug.exceptions.BadRequest(
            'Unknown dataset job_id "%s"' % form.dataset.data)

    # sweeps will be a list of the the permutations of swept fields
    # Get swept learning_rate
    sweeps = [{'learning_rate': v} for v in form.learning_rate.data]
    add_learning_rate = len(form.learning_rate.data) > 1

    # Add swept batch_size
    sweeps = [dict(s.items() + [('batch_size', bs)]) for bs in form.batch_size.data for s in sweeps[:]]
    add_batch_size = len(form.batch_size.data) > 1
    n_jobs = len(sweeps)
    jobs = []
    for sweep in sweeps:
        # Populate the form with swept data to be used in saving and
        # launching jobs.
        form.learning_rate.data = sweep['learning_rate']
        form.batch_size.data = sweep['batch_size']

        # Augment Job Name
        extra = ''
        if add_learning_rate:
            extra += ' learning_rate:%s' % str(form.learning_rate.data[0])
        if add_batch_size:
            extra += ' batch_size:%d' % form.batch_size.data[0]

        job = None
        try:
            job = GenericImageModelJob(
                username=utils.auth.get_username(),
                name=form.model_name.data + extra,
                group=form.group_name.data,
                dataset_id=datasetJob.id(),
            )
            # get framework (hard-coded to caffe for now)
            ######################################################
            # if hasattr(datasetJob, 'extension_id'):
            # if datasetJob.extension_id == 'ssd_pascal':
            if form.train_server_ip.data and form.train_server_port.data:
                ### framework to execute task in other servers
                fw = frameworks.get_framework_by_id('distrib_caffe')
            else:
                ### framework to execute local task
                fw = frameworks.get_framework_by_id(form.framework.data)
            ######################################################

            pretrained_model = None
            network_type = 'default'
            network_text = 'empty network'
            ######################################################
            if form.method.data == 'standard':
                found = False

                # can we find it in standard networks?
                network_desc = fw.get_standard_network_desc(form.standard_networks.data)

                # print 'network_desc', network_desc.__dict__
                if network_desc:
                    found = True
                    network = fw.get_network_from_desc(network_desc)
                ######################################################
                    network_type = form.standard_networks.data
                    network_text = network_desc
                ######################################################

                if not found:
                    raise werkzeug.exceptions.BadRequest(
                        'Unknown standard model "%s"' % form.standard_networks.data)
            elif form.method.data == 'previous':
                old_job = scheduler.get_job(form.previous_networks.data)

                if not old_job:
                    raise werkzeug.exceptions.BadRequest(
                        'Job not found: %s' % form.previous_networks.data)
            ######################################################
            # if form.method.data == 'previous':
            #     old_job = scheduler.get_job(form.previous_networks.data)
            #     if not old_job:
            #         raise werkzeug.exceptions.BadRequest(
            #             'Job not found: %s' % form.previous_networks.data)

                use_same_dataset = (old_job.dataset_id == job.dataset_id)
                network = fw.get_network_from_previous(old_job.train_task().network, use_same_dataset)


                for choice in form.previous_networks.choices:
                    if choice[0] == form.previous_networks.data:
                        epoch = float(flask.request.form['%s-snapshot' % form.previous_networks.data])
                        if epoch == 0:
                            pass
                        elif epoch == -1:
                            pretrained_model = old_job.train_task().pretrained_model
                        else:
                            # verify snapshot exists
                            pretrained_model = old_job.train_task().get_snapshot(epoch, download=True)
                            if pretrained_model is None:
                                raise werkzeug.exceptions.BadRequest(
                                    "For the job %s, selected pretrained_model for epoch %d is invalid!"
                                    % (form.previous_networks.data, epoch))

                            # the first is the actual file if a list is returned, other should be meta data
                            if isinstance(pretrained_model, list):
                                pretrained_model = pretrained_model[0]

                            if not (os.path.exists(pretrained_model)):
                                raise werkzeug.exceptions.BadRequest(
                                    "Pretrained_model for the selected epoch doesn't exist. "
                                    "May be deleted by another user/process. "
                                    "Please restart the server to load the correct pretrained_model details.")
                            # get logical path
                            pretrained_model = old_job.train_task().get_snapshot(epoch)
                        break
            elif form.method.data == 'pretrained':
                pretrained_job = scheduler.get_job(form.pretrained_networks.data)
                model_def_path = pretrained_job.get_model_def_path()
                weights_path = pretrained_job.get_weights_path()

                network = fw.get_network_from_path(model_def_path)
                pretrained_model = weights_path

            elif form.method.data == 'custom':
                network = fw.get_network_from_desc(form.custom_network.data)
                pretrained_model = form.custom_network_snapshot.data.strip()
            ######################################################
                network_type = 'custom'
                network_text = form.custom_network.data
            ######################################################

            else:
                raise werkzeug.exceptions.BadRequest(
                    'Unrecognized method: "%s"' % form.method.data)

            policy = {'policy': form.lr_policy.data}
            if form.lr_policy.data == 'fixed':
                pass
            elif form.lr_policy.data == 'step':
                policy['stepsize'] = form.lr_step_size.data
                policy['gamma'] = form.lr_step_gamma.data
            elif form.lr_policy.data == 'multistep':
                policy['stepvalue'] = form.lr_multistep_values.data
                policy['gamma'] = form.lr_multistep_gamma.data
            elif form.lr_policy.data == 'exp':
                policy['gamma'] = form.lr_exp_gamma.data
            elif form.lr_policy.data == 'inv':
                policy['gamma'] = form.lr_inv_gamma.data
                policy['power'] = form.lr_inv_power.data
            elif form.lr_policy.data == 'poly':
                policy['power'] = form.lr_poly_power.data
            elif form.lr_policy.data == 'sigmoid':
                policy['stepsize'] = form.lr_sigmoid_step.data
                policy['gamma'] = form.lr_sigmoid_gamma.data
            else:
                raise werkzeug.exceptions.BadRequest(
                    'Invalid learning rate policy')

            if config_value('caffe')['multi_gpu']:
                if form.select_gpu_count.data:
                    gpu_count = form.select_gpu_count.data
                    selected_gpus = None
                else:
                    selected_gpus = [str(gpu) for gpu in form.select_gpus.data]
                    gpu_count = None
            else:
                if form.select_gpu.data == 'next':
                    gpu_count = 1
                    selected_gpus = None
                else:
                    selected_gpus = [str(form.select_gpu.data)]
                    gpu_count = None

            # Set up data augmentation structure
            data_aug = {}
            data_aug['flip'] = form.aug_flip.data
            data_aug['quad_rot'] = form.aug_quad_rot.data
            data_aug['rot'] = form.aug_rot.data
            data_aug['scale'] = form.aug_scale.data
            data_aug['noise'] = form.aug_noise.data
            data_aug['contrast'] = form.aug_contrast.data
            data_aug['whitening'] = form.aug_whitening.data
            data_aug['hsv_use'] = form.aug_hsv_use.data
            data_aug['hsv_h'] = form.aug_hsv_h.data
            data_aug['hsv_s'] = form.aug_hsv_s.data
            data_aug['hsv_v'] = form.aug_hsv_v.data

            # Python Layer File may be on the server or copied from the client.
            fs.copy_python_layer_file(
                bool(form.python_layer_from_client.data),
                job.dir(),
                (flask.request.files[form.python_layer_client_file.name]
                 if form.python_layer_client_file.name in flask.request.files
                 else ''), form.python_layer_server_file.data)
            if form.train_server_ip.data and form.train_server_port.data:
                try:
                    job.tasks.append(fw.create_train_task(
                        job=job,
                        dataset=datasetJob,
                        train_epochs=form.train_epochs.data,
                        snapshot_interval=form.snapshot_interval.data,
                        learning_rate=form.learning_rate.data[0],
                        lr_policy=policy,
                        gpu_count=gpu_count,
                        selected_gpus=selected_gpus,
                        batch_size=form.batch_size.data[0],
                        batch_accumulation=form.batch_accumulation.data,
                        val_interval=form.val_interval.data,
                        traces_interval=form.traces_interval.data,
                        pretrained_model=pretrained_model,
                        crop_size=form.crop_size.data,
                        use_mean=form.use_mean.data,
                        network=network,
                        random_seed=form.random_seed.data,
                        solver_type=form.solver_type.data,
                        rms_decay=form.rms_decay.data,
                        shuffle=form.shuffle.data,
                        data_aug=data_aug,
                        ###############
                        max_iter_num = form.max_iter_num.data,
                        data_dir=datasetJob._dir,
                        test_batch_size=form.batch_size.data[0],
                        network_type=network_type,
                        network_text = network_text,
                        train_server_ip = form.train_server_ip.data,
                        train_server_port = form.train_server_port.data,
                        ###############
                    ))
                except:
                    print 'server job error'
                    raise Exception

            else:
                try:
                    job.tasks.append(fw.create_train_task(
                        job=job,
                        dataset=datasetJob,
                        train_epochs=form.train_epochs.data,
                        snapshot_interval=form.snapshot_interval.data,
                        learning_rate=form.learning_rate.data[0],
                        lr_policy=policy,
                        gpu_count=gpu_count,
                        selected_gpus=selected_gpus,
                        batch_size=form.batch_size.data[0],
                        batch_accumulation=form.batch_accumulation.data,
                        val_interval=form.val_interval.data,
                        traces_interval=form.traces_interval.data,
                        pretrained_model=pretrained_model,
                        crop_size=form.crop_size.data,
                        use_mean=form.use_mean.data,
                        network=network,
                        random_seed=form.random_seed.data,
                        solver_type=form.solver_type.data,
                        rms_decay=form.rms_decay.data,
                        shuffle=form.shuffle.data,
                        data_aug=data_aug,
                    ))
                except:
                    print 'local job error'
                    raise Exception

            # Save form data with the job so we can easily clone it later.
            save_form_to_job(job, form)
            jobs.append(job)
            scheduler.add_job(job)

            if n_jobs == 1:
                if request_wants_json():
                    return flask.jsonify(job.json_dict())
                else:
                    return flask.redirect(flask.url_for('digits.model.views.show', job_id=job.id()))

        except:
            if job:
                scheduler.delete_job(job)
            raise

    if request_wants_json():
        return flask.jsonify(jobs=[j.json_dict() for j in jobs])

    # If there are multiple jobs launched, go to the home page.
    return flask.redirect('/')


def show(job, related_jobs=None):
    """
    Called from digits.model.views.models_show()
    """
    data_extensions = get_data_extensions()
    view_extensions = get_view_extensions()

    return flask.render_template(
        'models/images/generic/show.html',
        job=job,
        data_extensions=data_extensions,
        view_extensions=view_extensions,
        related_jobs=related_jobs,
        # ######
        performance_heading = 'None',
        performance_data = {},
        # ######
    )


@blueprint.route('/timeline_tracing', methods=['GET'])
def timeline_tracing():
    """
    Shows timeline trace of a model
    """
    job = job_from_request()

    return flask.render_template('models/timeline_tracing.html', job=job)


@blueprint.route('/large_graph', methods=['GET'])
def large_graph():
    """
    Show the loss/accuracy graph, but bigger
    """
    job = job_from_request()

    return flask.render_template('models/large_graph.html', job=job)


@blueprint.route('/infer_one.json', methods=['POST'])
@blueprint.route('/infer_one', methods=['POST', 'GET'])
def infer_one():
    """
    Infer one image
    """
    model_job = job_from_request()

    remove_image_path = False
    if 'image_path' in flask.request.form and flask.request.form['image_path']:
        image_path = flask.request.form['image_path']
    elif 'image_file' in flask.request.files and flask.request.files['image_file']:
        outfile = tempfile.mkstemp(suffix='.bin')
        flask.request.files['image_file'].save(outfile[1])
        image_path = outfile[1]
        os.close(outfile[0])
        remove_image_path = True
    else:
        raise werkzeug.exceptions.BadRequest('must provide image_path or image_file')

    epoch = None
    if 'snapshot_epoch' in flask.request.form:
        epoch = float(flask.request.form['snapshot_epoch'])

    layers = 'none'
    if 'show_visualizations' in flask.request.form and flask.request.form['show_visualizations']:
        layers = 'all'

    if 'dont_resize' in flask.request.form and flask.request.form['dont_resize']:
        resize = False
    else:
        resize = True

    # create inference job
    inference_job = ImageInferenceJob(
        username=utils.auth.get_username(),
        name="Infer One Image",
        model=model_job,
        images=[image_path],
        epoch=epoch,
        layers=layers,
        resize=resize,
    )

    # schedule tasks
    scheduler.add_job(inference_job)

    # wait for job to complete
    inference_job.wait_completion()

    # retrieve inference data
    inputs, outputs, model_visualization = inference_job.get_data()

    # set return status code
    status_code = 500 if inference_job.status == 'E' else 200

    # delete job folder and remove from scheduler list
    scheduler.delete_job(inference_job)

    if remove_image_path:
        os.remove(image_path)

    if inputs is not None and len(inputs['data']) == 1:
        image = utils.image.embed_image_html(inputs['data'][0])
        visualizations, header_html, app_begin_html, app_end_html = get_inference_visualizations(
            model_job.dataset,
            inputs,
            outputs)
        inference_view_html = visualizations[0]
    else:
        image = None
        inference_view_html = None
        header_html = None
        app_begin_html = None
        app_end_html = None

    if request_wants_json():
        return flask.jsonify({'outputs': dict((name, blob.tolist())
                                              for name, blob in outputs.iteritems())}), status_code
    else:
        return flask.render_template(
            'models/images/generic/infer_one.html',
            model_job=model_job,
            job=inference_job,
            image_src=image,
            inference_view_html=inference_view_html,
            header_html=header_html,
            app_begin_html=app_begin_html,
            app_end_html=app_end_html,
            visualizations=model_visualization,
            total_parameters=sum(v['param_count'] for v in model_visualization
                                 if v['vis_type'] == 'Weights'),
        ), status_code


@blueprint.route('/infer_extension.json', methods=['POST'])
@blueprint.route('/infer_extension', methods=['POST', 'GET'])
def infer_extension():
    """
    Perform inference using the data from an extension inference form
    """
    model_job = job_from_request()

    inference_db_job = None
    try:
        if 'data_extension_id' in flask.request.form:
            data_extension_id = flask.request.form['data_extension_id']
        else:
            data_extension_id = model_job.dataset.extension_id

        # create an inference database
        inference_db_job = create_inference_db(model_job, data_extension_id)
        db_path = inference_db_job.get_feature_db_path(constants.TEST_DB)

        # create database creation job
        epoch = None
        if 'snapshot_epoch' in flask.request.form:
            epoch = float(flask.request.form['snapshot_epoch'])

        layers = 'none'
        if 'show_visualizations' in flask.request.form and flask.request.form['show_visualizations']:
            layers = 'all'

        # create inference job
        inference_job = ImageInferenceJob(
            username=utils.auth.get_username(),
            name="Inference",
            model=model_job,
            images=db_path,
            epoch=epoch,
            layers=layers,
            resize=False,
        )

        # schedule tasks
        scheduler.add_job(inference_job)

        # wait for job to complete
        inference_job.wait_completion()

    finally:
        if inference_db_job:
            scheduler.delete_job(inference_db_job)

    # retrieve inference data
    inputs, outputs, model_visualization = inference_job.get_data()

    # set return status code
    status_code = 500 if inference_job.status == 'E' else 200

    # delete job folder and remove from scheduler list
    scheduler.delete_job(inference_job)

    if outputs is not None and len(outputs) < 1:
        # an error occurred
        outputs = None

    if inputs is not None:
        keys = [str(idx) for idx in inputs['ids']]
        inference_views_html, header_html, app_begin_html, app_end_html = get_inference_visualizations(
            model_job.dataset,
            inputs,
            outputs)
    else:
        inference_views_html = None
        header_html = None
        keys = None
        app_begin_html = None
        app_end_html = None

    if request_wants_json():
        result = {}
        for i, key in enumerate(keys):
            result[key] = dict((name, blob[i].tolist()) for name, blob in outputs.iteritems())
        return flask.jsonify({'outputs': result}), status_code
    else:
        return flask.render_template(
            'models/images/generic/infer_extension.html',
            model_job=model_job,
            job=inference_job,
            keys=keys,
            inference_views_html=inference_views_html,
            header_html=header_html,
            app_begin_html=app_begin_html,
            app_end_html=app_end_html,
            visualizations=model_visualization,
            total_parameters=sum(v['param_count'] for v in model_visualization
                                 if v['vis_type'] == 'Weights'),
        ), status_code


@blueprint.route('/infer_db.json', methods=['POST'])
@blueprint.route('/infer_db', methods=['POST', 'GET'])
def infer_db():
    """
    Infer a database
    """
    model_job = job_from_request()


    if 'db_path' not in flask.request.form or flask.request.form['db_path'] is None:
        raise werkzeug.exceptions.BadRequest('db_path is a required field')

    db_path = flask.request.form['db_path']

 
    if not os.path.exists(db_path):
        raise werkzeug.exceptions.BadRequest('DB "%s" does not exit' % db_path)

    epoch = None
    if 'snapshot_epoch' in flask.request.form:
        epoch = float(flask.request.form['snapshot_epoch'])

    if 'dont_resize' in flask.request.form and flask.request.form['dont_resize']:
        resize = False
    else:
        resize = True

    # create inference job
    inference_job = ImageInferenceJob(
        username=utils.auth.get_username(),
        name="Infer Many Images",
        model=model_job,
        images=db_path,
        epoch=epoch,
        layers='none',
        resize=resize,
    )

    # schedule tasks
    scheduler.add_job(inference_job)

    # wait for job to complete
    inference_job.wait_completion()

    # retrieve inference data
    inputs, outputs, _ = inference_job.get_data()

    # set return status code
    status_code = 500 if inference_job.status == 'E' else 200

    # delete job folder and remove from scheduler list
    scheduler.delete_job(inference_job)

    if outputs is not None and len(outputs) < 1:
        # an error occurred
        outputs = None

    if inputs is not None:
        keys = [str(idx) for idx in inputs['ids']]
        inference_views_html, header_html, app_begin_html, app_end_html = get_inference_visualizations(
            model_job.dataset,
            inputs,
            outputs)
    else:
        inference_views_html = None
        header_html = None
        keys = None
        app_begin_html = None
        app_end_html = None

    if request_wants_json():
        result = {}
        for i, key in enumerate(keys):
            result[key] = dict((name, blob[i].tolist()) for name, blob in outputs.iteritems())
        return flask.jsonify({'outputs': result}), status_code
    else:
        return flask.render_template(
            'models/images/generic/infer_db.html',
            model_job=model_job,
            job=inference_job,
            keys=keys,
            inference_views_html=inference_views_html,
            header_html=header_html,
            app_begin_html=app_begin_html,
            app_end_html=app_end_html,
        ), status_code


@blueprint.route('/infer_many.json', methods=['POST'])
@blueprint.route('/infer_many', methods=['POST', 'GET'])
def infer_many():
    """
    Infer many images
    """
    model_job = job_from_request()

    image_list = flask.request.files.get('image_list')
    if not image_list:
        raise werkzeug.exceptions.BadRequest('image_list is a required field')

    if 'image_folder' in flask.request.form and flask.request.form['image_folder'].strip():
        image_folder = flask.request.form['image_folder']
        if not os.path.exists(image_folder):
            raise werkzeug.exceptions.BadRequest('image_folder "%s" does not exit' % image_folder)
    else:
        image_folder = None

    if 'num_test_images' in flask.request.form and flask.request.form['num_test_images'].strip():
        num_test_images = int(flask.request.form['num_test_images'])
    else:
        num_test_images = None

    epoch = None
    if 'snapshot_epoch' in flask.request.form:
        epoch = float(flask.request.form['snapshot_epoch'])

    if 'dont_resize' in flask.request.form and flask.request.form['dont_resize']:
        resize = False
    else:
        resize = True

    paths = []

    for line in image_list.readlines():
        line = line.strip()
        if not line:
            continue

        path = None
        # might contain a numerical label at the end
        match = re.match(r'(.*\S)\s+\d+$', line)
        if match:
            path = match.group(1)
        else:
            path = line

        if not utils.is_url(path) and image_folder and not os.path.isabs(path):
            path = os.path.join(image_folder, path)
        paths.append(path)

        if num_test_images is not None and len(paths) >= num_test_images:
            break

    # create inference job
    inference_job = ImageInferenceJob(
        username=utils.auth.get_username(),
        name="Infer Many Images",
        model=model_job,
        images=paths,
        epoch=epoch,
        layers='none',
        resize=resize,
    )

    # schedule tasks
    scheduler.add_job(inference_job)

    # wait for job to complete
    inference_job.wait_completion()

    # retrieve inference data
    inputs, outputs, _ = inference_job.get_data()

    # set return status code
    status_code = 500 if inference_job.status == 'E' else 200

    # delete job folder and remove from scheduler list
    scheduler.delete_job(inference_job)

    if outputs is not None and len(outputs) < 1:
        # an error occurred
        outputs = None

    if inputs is not None:
        paths = [paths[idx] for idx in inputs['ids']]
        inference_views_html, header_html, app_begin_html, app_end_html = get_inference_visualizations(
            model_job.dataset,
            inputs,
            outputs)
    else:
        inference_views_html = None
        header_html = None
        app_begin_html = None
        app_end_html = None

    if request_wants_json():
        result = {}
        for i, path in enumerate(paths):
            result[path] = dict((name, blob[i].tolist()) for name, blob in outputs.iteritems())
        return flask.jsonify({'outputs': result}), status_code
    else:
        return flask.render_template(
            'models/images/generic/infer_many.html',
            model_job=model_job,
            job=inference_job,
            paths=paths,
            inference_views_html=inference_views_html,
            header_html=header_html,
            app_begin_html=app_begin_html,
            app_end_html=app_end_html,
        ), status_code


def create_inference_db(model_job, data_extension_id):
    # create instance of extension class
    extension_class = extensions.data.get_extension(data_extension_id)
    if hasattr(model_job.dataset, 'extension_userdata'):
        extension_userdata = model_job.dataset.extension_userdata
    else:
        extension_userdata = {}
    extension_userdata.update({'is_inference_db': True})
    extension = extension_class(**extension_userdata)

    extension_form = extension.get_inference_form()
    extension_form_valid = extension_form.validate_on_submit()

    if not extension_form_valid:
        errors = extension_form.errors.copy()
        raise werkzeug.exceptions.BadRequest(repr(errors))

    extension.userdata.update(extension_form.data)

    # create job
    job = GenericDatasetJob(
        username=utils.auth.get_username(),
        name='Inference dataset',
        group=None,
        backend='lmdb',
        feature_encoding='none',
        label_encoding='none',
        batch_size=1,
        num_threads=1,
        force_same_shape=0,
        extension_id=data_extension_id,
        extension_userdata=extension.get_user_data(),
    )

    # schedule tasks and wait for job to complete
    scheduler.add_job(job)
    job.wait_completion()

    # check for errors
    if job.status != Status.DONE:
        msg = ""
        for task in job.tasks:
            if task.exception:
                msg = msg + task.exception
            if task.traceback:
                msg = msg + task.exception
        raise RuntimeError(msg)

    return job


def get_datasets(extension_id):
    if extension_id:
        jobs = [j for j in scheduler.jobs.values()
                if isinstance(j, GenericDatasetJob) and
                j.extension_id == extension_id and (j.status.is_running() or j.status == Status.DONE)]
    else:
        jobs = [j for j in scheduler.jobs.values()
                if (isinstance(j, GenericImageDatasetJob) or isinstance(j, GenericDatasetJob)) and
                (j.status.is_running() or j.status == Status.DONE)]
    return [(j.id(), j.name())
            for j in sorted(jobs, cmp=lambda x, y: cmp(y.id(), x.id()))]


def get_inference_visualizations(dataset, inputs, outputs):
    # get extension ID from form and retrieve extension class
    if 'view_extension_id' in flask.request.form:
        view_extension_id = flask.request.form['view_extension_id']
        extension_class = extensions.view.get_extension(view_extension_id)
        if extension_class is None:
            raise ValueError("Unknown extension '%s'" % view_extension_id)
    else:
        # no view extension specified, use default
        extension_class = extensions.view.get_default_extension()
    extension_form = extension_class.get_config_form()

    # validate form
    extension_form_valid = extension_form.validate_on_submit()
    if not extension_form_valid:
        raise ValueError("Extension form validation failed with %s" % repr(extension_form.errors))

    # create instance of extension class
    extension = extension_class(dataset, **extension_form.data)

    visualizations = []
    # process data
    n = len(inputs['ids'])
    for idx in xrange(n):
        input_id = inputs['ids'][idx]
        input_data = inputs['data'][idx]
        output_data = {key: outputs[key][idx] for key in outputs}
        data = extension.process_data(
            input_id,
            input_data,
            output_data)
        template, context = extension.get_view_template(data)
        visualizations.append(
            flask.render_template_string(template, **context))
    # get header
    template, context = extension.get_header_template()
    header = flask.render_template_string(template, **context) if template else None
    app_begin, app_end = extension.get_ng_templates()
    return visualizations, header, app_begin, app_end


def get_previous_networks():
    return [(j.id(), j.name()) for j in sorted(
        [j for j in scheduler.jobs.values() if isinstance(j, GenericImageModelJob)],
        cmp=lambda x, y: cmp(y.id(), x.id())
    )
    ]


def get_previous_networks_fulldetails():
    return [(j) for j in sorted(
        [j for j in scheduler.jobs.values() if isinstance(j, GenericImageModelJob)],
        cmp=lambda x, y: cmp(y.id(), x.id())
    )
    ]


def get_previous_network_snapshots():
    prev_network_snapshots = []
    for job_id, _ in get_previous_networks():
        job = scheduler.get_job(job_id)
        e = [(0, 'None')] + [(epoch, 'Epoch #%s' % epoch)
                             for _, epoch in reversed(job.train_task().snapshots)]
        if job.train_task().pretrained_model:
            e.insert(0, (-1, 'Previous pretrained model'))
        prev_network_snapshots.append(e)
    return prev_network_snapshots


def get_pretrained_networks():
    return [(j.id(), j.name()) for j in sorted(
        [j for j in scheduler.jobs.values() if isinstance(j, PretrainedModelJob)],
        cmp=lambda x, y: cmp(y.id(), x.id())
    )
    ]


def get_pretrained_networks_fulldetails():
    return [(j) for j in sorted(
        [j for j in scheduler.jobs.values() if isinstance(j, PretrainedModelJob)],
        cmp=lambda x, y: cmp(y.id(), x.id())
    )
    ]


def get_data_extensions():
    """
    return all enabled data extensions
    """
    data_extensions = {"all-default": "Default"}
    all_extensions = extensions.data.get_extensions()
    for extension in all_extensions:
        data_extensions[extension.get_id()] = extension.get_title()
    return data_extensions


def get_view_extensions():
    """
    return all enabled view extensions
    """
    view_extensions = {}
    all_extensions = extensions.view.get_extensions()
    for extension in all_extensions:
        view_extensions[extension.get_id()] = extension.get_title()
    return view_extensions


#################
@blueprint.route('/cal_performance_data.json', methods=['POST'])
@blueprint.route('/cal_performance_data', methods=['POST', 'GET'])
def cal_performance_data():
    from digits.job_client import cal_map

    if 'sp_pic_dir' in flask.request.form :
        sp_pic_dir = flask.request.form['sp_pic_dir']
    else:
         raise werkzeug.exceptions.BadRequest('pictues path is a required field')

    if 'gt_lbl_dir' in flask.request.form:
        gt_lbl_dir = flask.request.form['gt_lbl_dir']
    else:
         raise werkzeug.exceptions.BadRequest('pictues path is a required field')

    performance_data = {}
    data_file_path = os.path.join( sp_pic_dir, '..', 'performance_data.txt' )
    pd_lbl_dir = os.path.join( sp_pic_dir, '..', 'labels_prediction' )
    # print pd_lbl_dir

    if not os.path.exists( sp_pic_dir ):
        raise werkzeug.exceptions.BadRequest('image dir is not found, please specify a valid folder')
    if not os.path.exists( pd_lbl_dir ):
        raise werkzeug.exceptions.BadRequest('prediction labels dir is not found, please get prediction first')
    if not os.path.exists( gt_lbl_dir ):
        raise werkzeug.exceptions.BadRequest('ground truth labels dir is not found, please specify a valid folder')

    cal_map.calculate_map(gt_lbl_dir, pd_lbl_dir)
    f = open ( data_file_path )
    all_lines = f.readlines()
    for cls_data_line in all_lines:
        cls_data = cls_data_line.split('|')
        performance_data[cls_data[0]] = ('<br>').join( cls_data[1:-1] )
    f.close()

    # print performance_data
    """
    Called from digits.model.views.models_show()
    """
    job = job_from_request()
    # return flask.redirect(flask.url_for('digits.model.views.show', job_id=job.id()))
    data_extensions = get_data_extensions()
    view_extensions = get_view_extensions()
    return flask.render_template(
        'models/images/generic/show.html',
        job=job,
        data_extensions=data_extensions,
        view_extensions=view_extensions,
        related_jobs=None,
        #######
        last_sp_pic_dir = sp_pic_dir,
        last_gt_lbl_dir = gt_lbl_dir,
        performance_heading = 'select a class',
        performance_data = performance_data,
        #######
    )
#################


#################
@blueprint.route('/get_label/<job_id>.json', methods=['POST'])
@blueprint.route('/get_label/<job_id>', methods=['POST', 'GET'])
# @blueprint.route('/get_label', methods=['GET'])
def get_label(job_id):
    from digits.job_client import save_labels
    from digits.job_client import job_client

    ###get address of server runs model 
    if 'test_server_ip' in flask.request.form:
        test_server_ip = flask.request.form['test_server_ip']
    else:
         raise werkzeug.exceptions.BadRequest(' "test server ip" is a required field')
    if 'test_server_port' in flask.request.form:
        test_server_port = flask.request.form['test_server_port']
    else:
         raise werkzeug.exceptions.BadRequest(' "test server port" is a required field')


    if test_server_ip:
        test_server_ip = str(test_server_ip)
    else:
        raise werkzeug.exceptions.BadRequest(' please fill in "test server ip"')

    if test_server_ip:
        test_server_port = int(test_server_port)
    else:
        raise werkzeug.exceptions.BadRequest(' please fill in "test server port"')
    
    test_server_addr = (test_server_ip, test_server_port)


    #### send model to the test server
    iter_num = -1
    # GET ?epoch=n
    if 'epoch' in flask.request.args:
        iter_num = str(flask.request.args['epoch'])

    # POST ?snapshot_epoch=n (from form)
    elif 'snapshot_epoch' in flask.request.form:
        iter_num = str   (flask.request.form['snapshot_epoch'])

    if 'job_dir' in flask.request.form:
        job_dir = flask.request.form['job_dir']

    try:
        print job_dir + '/server_job_info.txt'
        f = open(job_dir + '/server_job_info.txt')
        server_job_info = f.readlines()
        training_server_ip = str( server_job_info[3].rstrip('\n') )
        training_server_port = int( server_job_info[4].rstrip('\n') )
        f.close()
    except:
        print 'server_download: cannot find server_job_info.txt'
        raise

    training_server_addr = (training_server_ip, training_server_port)

    job_client.test_request(training_server_addr, test_server_addr, job_id, iter_num)
    ####

    from PIL import ImageDraw, Image, ImageFont
    if 'sp_pic_dir' in flask.request.form:
        sp_pic_dir = flask.request.form['sp_pic_dir']
    else:
         raise werkzeug.exceptions.BadRequest('pictues path is a required field')


    ###get img name list
    if os.path.exists(sp_pic_dir):
        img_names = os.listdir(sp_pic_dir)
    else:
        raise werkzeug.exceptions.BadRequest('plese fill in "pictures path" ')

    ###get img width and height 
    img_path_0 = os.path.join( sp_pic_dir, img_names[0] )
    img = Image.open(img_path_0)
    img_w = img.size[0]
    img_h = img.size[1]
    # print img_w, img_h
    # ip = "localhost"
    # ip = "118.201.243.15"
    # port = 2133
    
    try:
        for img_name in img_names:
            img_path = os.path.join( sp_pic_dir, img_name )
            save_labels.get_response_label(img_path, img_w, img_h, test_server_addr)
    except Exception as e:
        return 'Error occurs while requesting testing server.<br>error: {}'.format(e)


    return 'Finish Detection'
    # data_extensions = get_data_extensions()
    # view_extensions = get_view_extensions()
    # return flask.render_template(
    #     'models/images/generic/show.html',
    #     job=job,
    #     data_extensions=data_extensions,
    #     view_extensions=view_extensions,
    #     related_jobs=related_jobs,
    #     # ######
    #     performance_data = None,
    #     # ######
    # )

#################


#################
@blueprint.route('/show_sample.json', methods=['POST'])
@blueprint.route('/show_sample', methods=['POST', 'GET'])
def show_sample():
    from PIL import ImageDraw, Image, ImageFont

    if 'sp_pic_dir' in flask.request.form:
        sp_pic_dir = flask.request.form['sp_pic_dir']
    else:
        sp_pic_dir = flask.request.args.get('sp_pic_dir', None)

    # read class labels
    labels = []
    performance_data_path = os.path.join( sp_pic_dir, '..', 'performance_data.txt')
    print performance_data_path
    if os.path.exists(performance_data_path):
        f = open(performance_data_path)

        all_lines = f.readlines()
        for cls_data_line in all_lines:
            cls_data = cls_data_line.split('|')
            labels.append(cls_data[0])
    else:
        print 'can not find performance_data.txt'

    job = job_from_request()
    db = 'test_images'
    total_offet = int(flask.request.args.get('size', 10))
    page = int(flask.request.args.get('page', 0))
    size = int(flask.request.args.get('size', 10))
    label = flask.request.args.get('label', None)

    if page < 0:
        page = 0

    if label is not None:
        try:
            label = int(label)
        except ValueError:
            label = None

    img_dir = sp_pic_dir
    fa_label_dir = os.path.join( sp_pic_dir, '..', 'labels_false_alarm')
    md_label_dir = os.path.join( sp_pic_dir, '..', 'labels_miss_detect')
    label_file_dir = os.path.join( sp_pic_dir, '..', 'labels_prediction')

    if label != None:     
        print 'label', label
        if labels != []:
            label_file_dir = os.path.join( sp_pic_dir, '..', ('labels_' + labels[label]) )

    ###get labls name list
    if os.path.exists(label_file_dir):
        filename_sets = os.listdir(label_file_dir)
    else:
        raise werkzeug.exceptions.BadRequest('labels_prediction is not found, please "get prediction" first')

    ###
    imgs = []
    filenames = sorted( filename_sets )
    # filenames = filename_sets
    img_suffixes = ['.jpg', '.JPG', '.png', '.PNG', '.bmp', '.BMP']
    
    total_entries = len(filenames)
    min_page = max(0, page - 5)
    max_page = min((total_entries - 1) / size, page + 5)
    pages = range(min_page, max_page + 1)

    count_begin = page * size
    count_end = (page + 1) * size
    ###drawing parameters
    font_size = 30
    rect_thick = 15 
    font = ImageFont.truetype('ubuntu_font_family/Ubuntu-B.ttf', font_size) ###systim font is /usr/share/font/truthtype/ubuntu_font_family/Ubuntu-B.ttf
    count = count_begin
    while count < count_end and count < total_entries:

        label_file = filenames[ count ]
        count += 1
        count_end_offset = 1
        # print 'count', count

        for img_suffix in img_suffixes:
            pd_lbl_dir = os.path.join( label_file_dir, label_file )
            img_path = os.path.join( img_dir, label_file.split('.')[0]) + img_suffix
            if os.path.exists(img_path) and os.path.exists(pd_lbl_dir):
                count_end_offset = 0

                img = Image.open(img_path)
                img_w = img.size[0]
                img_h = img.size[1]
                ###read label file and draw labels
                f = open(pd_lbl_dir)
                lines = f.readlines()
                num_obj = lines[0]

                for n in range(1, int(num_obj)+1):
                    items = lines[n].split()
                    x_Ltop = int( float(items[1]) * img_w )
                    y_Ltop = int( float(items[2]) * img_h )
                    x_Rbtm = int( float(items[3]) * img_w )
                    y_Rbtm = int( float(items[4]) * img_h )
                    # write down label on image
                    write = ImageDraw.Draw(img)
                    write.text( ( (x_Ltop - font_size*0.5) if (img_w - x_Ltop) > font_size*2 else (x_Ltop - font_size*2), 
                        (y_Ltop - font_size * 1.5) if (y_Ltop - font_size * 1.5) > 0 else (y_Rbtm + font_size*0.5) ), 
                        items[0], font = font, fill = 'green')

                    # draw boxes
                    mask = Image.new('1', img.size)
                    draw = ImageDraw.Draw(mask)
                    for pix in (rect_thick, -rect_thick+1):
                        x_Ltop -= pix /2
                        y_Ltop -= pix /2
                        x_Rbtm += pix /2
                        y_Rbtm += pix /2
                        draw.rectangle( ( (x_Ltop, y_Ltop , x_Rbtm, y_Rbtm) ), fill = (pix+rect_thick-1 and 255) )
                    img.paste('green', mask = mask)
                f.close()
                
                ###draw false labels if existed
                fa_lbl_path = os.path.join( fa_label_dir, label_file )
                if os.path.exists(fa_lbl_path):
                    f = open(fa_lbl_path)
                    lines = f.readlines()
                    num_obj = lines[0]
                    for n in range(1, int(num_obj)+1):
                        items = lines[n].split()
                        if label != None:
                            if items[0] != labels[label]:
                                continue
                        x_Ltop = int( float(items[1]) * img_w )
                        y_Ltop = int( float(items[2]) * img_h )
                        x_Rbtm = int( float(items[3]) * img_w )
                        y_Rbtm = int( float(items[4]) * img_h )
                        write = ImageDraw.Draw(img)
                        write.text( ( (x_Ltop - font_size*0.5) if (img_w - x_Ltop) > font_size*2 else (x_Ltop - font_size*2), 
                            (y_Ltop - font_size * 1.5) if (y_Ltop - font_size * 1.5) > 0 else (y_Rbtm + font_size*0.5) ), 
                            items[0], font = font, fill = 'orange')

                        # draw boxes
                        mask = Image.new('1', img.size)
                        draw = ImageDraw.Draw(mask)
                        for pix in (rect_thick, -rect_thick+1):
                            x_Ltop -= pix /2
                            y_Ltop -= pix /2
                            x_Rbtm += pix /2
                            y_Rbtm += pix /2
                            draw.rectangle( ( (x_Ltop, y_Ltop , x_Rbtm, y_Rbtm) ), fill = (pix+rect_thick-1 and 255) )
                        img.paste('orange', mask = mask)
                    f.close()

                ###draw miss detected labels if existed
                md_lbl_path = os.path.join( md_label_dir, label_file )
                if os.path.exists(md_lbl_path):
                    f = open(md_lbl_path)
                    lines = f.readlines()
                    num_obj = lines[0]
                    for n in range(1, int(num_obj)+1):
                        items = lines[n].split()
                        if label != None:
                            if items[0] != labels[label]:
                                continue
                        x_Ltop = int( float(items[1]) * img_w )
                        y_Ltop = int( float(items[2]) * img_h )
                        x_Rbtm = int( float(items[3]) * img_w )
                        y_Rbtm = int( float(items[4]) * img_h )

                        write = ImageDraw.Draw(img)
                        write.text( ( (x_Ltop - font_size*0.5) if (img_w - x_Ltop) > font_size*2 else (x_Ltop - font_size*2), 
                            (y_Ltop - font_size * 1.5) if (y_Ltop - font_size * 1.5) > 0 else (y_Rbtm + font_size*0.5) ), 
                            items[0], font = font, fill = 'red')

                        #draw boxes
                        mask = Image.new('1', img.size)
                        draw = ImageDraw.Draw(mask)
                        for pix in (rect_thick, -rect_thick+1):
                            x_Ltop -= pix /2
                            y_Ltop -= pix /2
                            x_Rbtm += pix /2
                            y_Rbtm += pix /2
                            draw.rectangle( ( (x_Ltop, y_Ltop , x_Rbtm, y_Rbtm) ), fill = (pix+rect_thick-1 and 255) )
                        img.paste('red', mask = mask)
                    f.close()
                ###save img to show
                imgs.append({"label": label_file.split('0')[-1].split('.')[0] + '(ground truth)', 
                    "b64": utils.image.embed_image_html(img)})

        count_end += count_end_offset
    
    total_offet += count_end - (page + 1) * size

    return flask.render_template(
        'models/images/explore.html',
        page=page, size=size, job=job, imgs=imgs, pages=pages, label=label, labels = labels,
        total_entries=total_entries, db=db, sp_pic_dir = sp_pic_dir,)
#################

#################
@blueprint.route('/http_server.json', methods=['POST'])
@blueprint.route('/http_server', methods=['POST', 'GET'])
def http_server():
    return redirect('http://localhost:1022/')
#################

#################

def get_standard_networks():
    return [
        # ('lenet', 'LeNet'),
        # ('alexnet', 'AlexNet'),
        # ('googlenet', 'GoogLeNet'),
        ('detection', 'Detection'),
        ('attributes', 'Attributes'),
        ('face', 'Face'),
    ]


def get_default_standard_network():
    return 'detection'

################
@blueprint.route('/upload/<job_id>', methods=['GET', 'POST'])
def upload(job_id):  # run after one  chunk is uploaded
    print job_id
    if flask.request.method == 'POST':

        upload_file = flask.request.files['file']
        task = flask.request.form.get('task_id')  # get file id in upload process
        chunk = flask.request.form.get('chunk', 0)  # get chunk number in all chunks
        filename = '%s%s' % (task, chunk)  # coustruct chunk id

        # raw_input('pause here')
        save_dir = '/home/wills/testImg'  #  dir to save file
        if not os.path.exists(save_dir):
            os.mkdir(save_dir)
        upload_file.save( save_dir + '/' + filename )  # save chunk in local path
            
    return flask.redirect(flask.url_for('digits.model.views.show', job_id=job_id))

# @blueprint.route('/upload_success/<extension_id>.json', methods=['POST'])
@blueprint.route('/upload_success/<job_id>', methods=['GET', 'POST'])
def upload_success(job_id):  # run after all the chunks is upload
    task = flask.request.args.get('task_id')
    ext = flask.request.args.get('ext', '')
    upload_type = flask.request.args.get('type')
    if len(ext) == 0 and upload_type:
        ext = upload_type.split('/')[1]
    ext = '' if len(ext) == 0 else '.%s' % ext  # construct file name
    chunk = 0

    save_dir = '/home/wills/testImg'  #  dir to save file
    file_path = save_dir + '/' + task + ext #  filename to save file
    
    target_file =  open( file_path, 'w' ) # crate new files
    while True:
        try:
            filename = save_dir + '/' + task + str(chunk)
            source_file = open(filename, 'r')  # open chunks in order
            target_file.write(source_file.read())  # fill the new file with chunks
            source_file.close()
        except IOError:
            break
        chunk += 1
        os.remove(filename)  # delect chunks
    target_file.close()

    extract_dir = save_dir + '/tasks'
    # dataset_dir = save_dir + '/' + 'dataset'
    if ext == '.zip':
        import zipfile
        """unzip zip file"""
        zip_file = zipfile.ZipFile(file_path)
        if  not os.path.isdir(extract_dir):
            os.mkdir(extract_dir)
        for names in zip_file.namelist():
            zip_file.extract(names, extract_dir)
        zip_file.close()
        # os.rename(extract_dir, dataset_dir)

    if ext == '.rar':
        print 'unrar'
        import rarfile
        """unrar zip file"""
        rar = rarfile.RarFile(file_path)
        if not os.path.isdir(extract_dir):
            os.mkdir(extract_dir)
        os.chdir(extract_dir)
        rar.extractall()
        rar.close()
        # os.rename(extract_dir, dataset_dir)
    # print '/home/wills/Projects/digits-ssd/digits/static/upload_file/%s%s' % (task, ext)
    return flask.redirect(flask.url_for('digits.model.views.show', job_id=job_id))

#################
@blueprint.route('/<job_id>/server_download',
                 methods=['GET', 'POST'],
                 defaults={'extension': 'tar.gz'})
@blueprint.route('/<job_id>/server_download.<extension>',
                 methods=['GET', 'POST'])
def server_download(job_id, extension):
    
    iter_num = -1
    # GET ?epoch=n
    if 'epoch' in flask.request.args:
        iter_num = str(flask.request.args['epoch'])

    # POST ?snapshot_epoch=n (from form)
    elif 'snapshot_epoch' in flask.request.form:
        iter_num = str(flask.request.form['snapshot_epoch'])

    if 'job_dir' in flask.request.form:
        job_dir = flask.request.form['job_dir']

    try:
        print job_dir + '/server_job_info.txt'
        f = open(job_dir + '/server_job_info.txt')
        server_job_info = f.readlines()
        server_ip = server_job_info[0].rstrip('\n')
        server_port = server_job_info[1].rstrip('\n')
        f.close()
    except:
        print 'server_download: cannot find server_job_info.txt'
        raise
    return redirect('http://{}:{}/{}/download?iter={}'.format(server_ip, server_port, job_id, iter_num))