# -*- coding: utf-8 -*-
# Generated by the protocol buffer compiler.  DO NOT EDIT!
# source: DisServ.proto
# Protobuf Python Version: 5.26.1
"""Generated protocol buffer code."""
from google.protobuf import descriptor as _descriptor
from google.protobuf import descriptor_pool as _descriptor_pool
from google.protobuf import symbol_database as _symbol_database
from google.protobuf.internal import builder as _builder
# @@protoc_insertion_point(imports)

_sym_db = _symbol_database.Default()




DESCRIPTOR = _descriptor_pool.Default().AddSerializedFile(b'\n\rDisServ.proto\x12\x07\x44isServ\"T\n\x11single_patch_item\x12\n\n\x02op\x18\x01 \x01(\x03\x12\x12\n\nstart_line\x18\x02 \x01(\x03\x12\x11\n\tcont_line\x18\x03 \x01(\x03\x12\x0c\n\x04\x63ont\x18\x04 \x03(\t\"\x97\x01\n\x05patch\x12\x12\n\ntime_stamp\x18\x01 \x01(\x03\x12$\n\tappli_usr\x18\x02 \x01(\x0b\x32\x11.DisServ.usr_info\x12)\n\tappli_doc\x18\x03 \x01(\x0b\x32\x16.DisServ.document_info\x12)\n\x05items\x18\x04 \x03(\x0b\x32\x1a.DisServ.single_patch_item\"#\n\nboolen_res\x12\x15\n\raccept_status\x18\x01 \x01(\x08\",\n\x08usr_info\x12\x10\n\x08usr_name\x18\x01 \x01(\t\x12\x0e\n\x06usr_ID\x18\x02 \x01(\x03\"1\n\tlogin_res\x12\x14\n\x0clogin_status\x18\x01 \x01(\x08\x12\x0e\n\x06usr_ID\x18\x02 \x01(\t\"Y\n\x08\x64ocument\x12(\n\x08\x64oc_info\x18\x01 \x01(\x0b\x32\x16.DisServ.document_info\x12\x12\n\ntime_stamp\x18\x02 \x01(\x03\x12\x0f\n\x07\x63ontent\x18\x03 \x03(\t\"N\n\rdocument_info\x12\x10\n\x08\x64oc_name\x18\x01 \x01(\t\x12\x16\n\x0e\x64oc_descriptor\x18\x02 \x01(\t\x12\x13\n\x0b\x64oc_ownerID\x18\x03 \x01(\x03\"9\n\x08\x64oc_list\x12-\n\rdoc_info_list\x18\x01 \x03(\x0b\x32\x16.DisServ.document_info2\xd6\x03\n\x07\x44isServ\x12.\n\x05login\x12\x11.DisServ.usr_info\x1a\x12.DisServ.login_res\x12\x30\n\x06logout\x12\x11.DisServ.usr_info\x1a\x13.DisServ.boolen_res\x12\x39\n\x0fupload_document\x12\x11.DisServ.document\x1a\x13.DisServ.boolen_res\x12>\n\x0frecall_document\x12\x16.DisServ.document_info\x1a\x13.DisServ.boolen_res\x12\x33\n\x0cupload_patch\x12\x0e.DisServ.patch\x1a\x13.DisServ.boolen_res\x12\x41\n\x14request_for_document\x12\x16.DisServ.document_info\x1a\x11.DisServ.document\x12\x35\n\x11request_for_patch\x12\x0e.DisServ.patch\x1a\x0e.DisServ.patch0\x01\x12?\n\x15request_for_sharelist\x12\x13.DisServ.boolen_res\x1a\x11.DisServ.doc_listb\x06proto3')

_globals = globals()
_builder.BuildMessageAndEnumDescriptors(DESCRIPTOR, _globals)
_builder.BuildTopDescriptorsAndMessages(DESCRIPTOR, 'DisServ_pb2', _globals)
if not _descriptor._USE_C_DESCRIPTORS:
  DESCRIPTOR._loaded_options = None
  _globals['_SINGLE_PATCH_ITEM']._serialized_start=26
  _globals['_SINGLE_PATCH_ITEM']._serialized_end=110
  _globals['_PATCH']._serialized_start=113
  _globals['_PATCH']._serialized_end=264
  _globals['_BOOLEN_RES']._serialized_start=266
  _globals['_BOOLEN_RES']._serialized_end=301
  _globals['_USR_INFO']._serialized_start=303
  _globals['_USR_INFO']._serialized_end=347
  _globals['_LOGIN_RES']._serialized_start=349
  _globals['_LOGIN_RES']._serialized_end=398
  _globals['_DOCUMENT']._serialized_start=400
  _globals['_DOCUMENT']._serialized_end=489
  _globals['_DOCUMENT_INFO']._serialized_start=491
  _globals['_DOCUMENT_INFO']._serialized_end=569
  _globals['_DOC_LIST']._serialized_start=571
  _globals['_DOC_LIST']._serialized_end=628
  _globals['_DISSERV']._serialized_start=631
  _globals['_DISSERV']._serialized_end=1101
# @@protoc_insertion_point(module_scope)
