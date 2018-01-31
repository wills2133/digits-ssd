# Generated by the protocol buffer compiler.  DO NOT EDIT!
# source: job_msg.proto

import sys
_b=sys.version_info[0]<3 and (lambda x:x) or (lambda x:x.encode('latin1'))
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from google.protobuf import reflection as _reflection
from google.protobuf import symbol_database as _symbol_database
from google.protobuf import descriptor_pb2
# @@protoc_insertion_point(imports)

_sym_db = _symbol_database.Default()




DESCRIPTOR = _descriptor.FileDescriptor(
  name='job_msg.proto',
  package='TrainingMsg',
  syntax='proto2',
  serialized_pb=_b('\n\rjob_msg.proto\x12\x0bTrainingMsg\"\xb5\x03\n\x07Request\x12\x0e\n\x06job_id\x18\x01 \x02(\t\x12-\n\x07\x63ommand\x18\x02 \x02(\x0e\x32\x1c.TrainingMsg.Request.Command\x12\x11\n\targuments\x18\x03 \x01(\t\x12\x0e\n\x06solver\x18\x04 \x01(\x0c\x12\x15\n\rtrain_val_net\x18\x05 \x01(\t\x12\x10\n\x08test_net\x18\x06 \x01(\t\x12\x14\n\x0cimage_folder\x18\x07 \x01(\t\x12/\n\x0cnetwork_type\x18\x08 \x01(\x0e\x32\x19.TrainingMsg.Request.Type\x12\x16\n\x0etest_server_ip\x18\t \x01(\t\x12\x18\n\x10test_server_port\x18\n \x01(\x05\x12\x12\n\nmodel_iter\x18\x0b \x01(\t\x12\x11\n\tmodel_seg\x18\x0c \x01(\x0c\"B\n\x07\x43ommand\x12\t\n\x05TRAIN\x10\x00\x12\t\n\x05\x41\x42ORT\x10\x01\x12\x0b\n\x07REQTEST\x10\x02\x12\x08\n\x04TEST\x10\x03\x12\n\n\x06\x44\x45LETE\x10\x04\";\n\x04Type\x12\r\n\tDETECTION\x10\x00\x12\x0e\n\nATTRIBUTES\x10\x01\x12\x08\n\x04\x46\x41\x43\x45\x10\x02\x12\n\n\x06\x43USTOM\x10\x03\"x\n\x08Response\x12\x10\n\x08line_num\x18\x01 \x01(\t\x12\x10\n\x08log_line\x18\x02 \x03(\t\x12\x0f\n\x07log_end\x18\x03 \x01(\x08\x12\x14\n\x0cmodel_exists\x18\x04 \x01(\x08\x12\x12\n\ntest_ready\x18\x05 \x01(\x08\x12\r\n\x05\x65rror\x18\x06 \x01(\t')
)
_sym_db.RegisterFileDescriptor(DESCRIPTOR)



_REQUEST_COMMAND = _descriptor.EnumDescriptor(
  name='Command',
  full_name='TrainingMsg.Request.Command',
  filename=None,
  file=DESCRIPTOR,
  values=[
    _descriptor.EnumValueDescriptor(
      name='TRAIN', index=0, number=0,
      options=None,
      type=None),
    _descriptor.EnumValueDescriptor(
      name='ABORT', index=1, number=1,
      options=None,
      type=None),
    _descriptor.EnumValueDescriptor(
      name='REQTEST', index=2, number=2,
      options=None,
      type=None),
    _descriptor.EnumValueDescriptor(
      name='TEST', index=3, number=3,
      options=None,
      type=None),
    _descriptor.EnumValueDescriptor(
      name='DELETE', index=4, number=4,
      options=None,
      type=None),
  ],
  containing_type=None,
  options=None,
  serialized_start=341,
  serialized_end=407,
)
_sym_db.RegisterEnumDescriptor(_REQUEST_COMMAND)

_REQUEST_TYPE = _descriptor.EnumDescriptor(
  name='Type',
  full_name='TrainingMsg.Request.Type',
  filename=None,
  file=DESCRIPTOR,
  values=[
    _descriptor.EnumValueDescriptor(
      name='DETECTION', index=0, number=0,
      options=None,
      type=None),
    _descriptor.EnumValueDescriptor(
      name='ATTRIBUTES', index=1, number=1,
      options=None,
      type=None),
    _descriptor.EnumValueDescriptor(
      name='FACE', index=2, number=2,
      options=None,
      type=None),
    _descriptor.EnumValueDescriptor(
      name='CUSTOM', index=3, number=3,
      options=None,
      type=None),
  ],
  containing_type=None,
  options=None,
  serialized_start=409,
  serialized_end=468,
)
_sym_db.RegisterEnumDescriptor(_REQUEST_TYPE)


_REQUEST = _descriptor.Descriptor(
  name='Request',
  full_name='TrainingMsg.Request',
  filename=None,
  file=DESCRIPTOR,
  containing_type=None,
  fields=[
    _descriptor.FieldDescriptor(
      name='job_id', full_name='TrainingMsg.Request.job_id', index=0,
      number=1, type=9, cpp_type=9, label=2,
      has_default_value=False, default_value=_b("").decode('utf-8'),
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      options=None),
    _descriptor.FieldDescriptor(
      name='command', full_name='TrainingMsg.Request.command', index=1,
      number=2, type=14, cpp_type=8, label=2,
      has_default_value=False, default_value=0,
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      options=None),
    _descriptor.FieldDescriptor(
      name='arguments', full_name='TrainingMsg.Request.arguments', index=2,
      number=3, type=9, cpp_type=9, label=1,
      has_default_value=False, default_value=_b("").decode('utf-8'),
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      options=None),
    _descriptor.FieldDescriptor(
      name='solver', full_name='TrainingMsg.Request.solver', index=3,
      number=4, type=12, cpp_type=9, label=1,
      has_default_value=False, default_value=_b(""),
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      options=None),
    _descriptor.FieldDescriptor(
      name='train_val_net', full_name='TrainingMsg.Request.train_val_net', index=4,
      number=5, type=9, cpp_type=9, label=1,
      has_default_value=False, default_value=_b("").decode('utf-8'),
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      options=None),
    _descriptor.FieldDescriptor(
      name='test_net', full_name='TrainingMsg.Request.test_net', index=5,
      number=6, type=9, cpp_type=9, label=1,
      has_default_value=False, default_value=_b("").decode('utf-8'),
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      options=None),
    _descriptor.FieldDescriptor(
      name='image_folder', full_name='TrainingMsg.Request.image_folder', index=6,
      number=7, type=9, cpp_type=9, label=1,
      has_default_value=False, default_value=_b("").decode('utf-8'),
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      options=None),
    _descriptor.FieldDescriptor(
      name='network_type', full_name='TrainingMsg.Request.network_type', index=7,
      number=8, type=14, cpp_type=8, label=1,
      has_default_value=False, default_value=0,
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      options=None),
    _descriptor.FieldDescriptor(
      name='test_server_ip', full_name='TrainingMsg.Request.test_server_ip', index=8,
      number=9, type=9, cpp_type=9, label=1,
      has_default_value=False, default_value=_b("").decode('utf-8'),
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      options=None),
    _descriptor.FieldDescriptor(
      name='test_server_port', full_name='TrainingMsg.Request.test_server_port', index=9,
      number=10, type=5, cpp_type=1, label=1,
      has_default_value=False, default_value=0,
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      options=None),
    _descriptor.FieldDescriptor(
      name='model_iter', full_name='TrainingMsg.Request.model_iter', index=10,
      number=11, type=9, cpp_type=9, label=1,
      has_default_value=False, default_value=_b("").decode('utf-8'),
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      options=None),
    _descriptor.FieldDescriptor(
      name='model_seg', full_name='TrainingMsg.Request.model_seg', index=11,
      number=12, type=12, cpp_type=9, label=1,
      has_default_value=False, default_value=_b(""),
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      options=None),
  ],
  extensions=[
  ],
  nested_types=[],
  enum_types=[
    _REQUEST_COMMAND,
    _REQUEST_TYPE,
  ],
  options=None,
  is_extendable=False,
  syntax='proto2',
  extension_ranges=[],
  oneofs=[
  ],
  serialized_start=31,
  serialized_end=468,
)


_RESPONSE = _descriptor.Descriptor(
  name='Response',
  full_name='TrainingMsg.Response',
  filename=None,
  file=DESCRIPTOR,
  containing_type=None,
  fields=[
    _descriptor.FieldDescriptor(
      name='line_num', full_name='TrainingMsg.Response.line_num', index=0,
      number=1, type=9, cpp_type=9, label=1,
      has_default_value=False, default_value=_b("").decode('utf-8'),
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      options=None),
    _descriptor.FieldDescriptor(
      name='log_line', full_name='TrainingMsg.Response.log_line', index=1,
      number=2, type=9, cpp_type=9, label=3,
      has_default_value=False, default_value=[],
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      options=None),
    _descriptor.FieldDescriptor(
      name='log_end', full_name='TrainingMsg.Response.log_end', index=2,
      number=3, type=8, cpp_type=7, label=1,
      has_default_value=False, default_value=False,
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      options=None),
    _descriptor.FieldDescriptor(
      name='model_exists', full_name='TrainingMsg.Response.model_exists', index=3,
      number=4, type=8, cpp_type=7, label=1,
      has_default_value=False, default_value=False,
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      options=None),
    _descriptor.FieldDescriptor(
      name='test_ready', full_name='TrainingMsg.Response.test_ready', index=4,
      number=5, type=8, cpp_type=7, label=1,
      has_default_value=False, default_value=False,
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      options=None),
    _descriptor.FieldDescriptor(
      name='error', full_name='TrainingMsg.Response.error', index=5,
      number=6, type=9, cpp_type=9, label=1,
      has_default_value=False, default_value=_b("").decode('utf-8'),
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      options=None),
  ],
  extensions=[
  ],
  nested_types=[],
  enum_types=[
  ],
  options=None,
  is_extendable=False,
  syntax='proto2',
  extension_ranges=[],
  oneofs=[
  ],
  serialized_start=470,
  serialized_end=590,
)

_REQUEST.fields_by_name['command'].enum_type = _REQUEST_COMMAND
_REQUEST.fields_by_name['network_type'].enum_type = _REQUEST_TYPE
_REQUEST_COMMAND.containing_type = _REQUEST
_REQUEST_TYPE.containing_type = _REQUEST
DESCRIPTOR.message_types_by_name['Request'] = _REQUEST
DESCRIPTOR.message_types_by_name['Response'] = _RESPONSE

Request = _reflection.GeneratedProtocolMessageType('Request', (_message.Message,), dict(
  DESCRIPTOR = _REQUEST,
  __module__ = 'job_msg_pb2'
  # @@protoc_insertion_point(class_scope:TrainingMsg.Request)
  ))
_sym_db.RegisterMessage(Request)

Response = _reflection.GeneratedProtocolMessageType('Response', (_message.Message,), dict(
  DESCRIPTOR = _RESPONSE,
  __module__ = 'job_msg_pb2'
  # @@protoc_insertion_point(class_scope:TrainingMsg.Response)
  ))
_sym_db.RegisterMessage(Response)


# @@protoc_insertion_point(module_scope)