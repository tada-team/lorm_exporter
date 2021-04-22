import datetime
import re

import django.apps
from django.contrib.postgres.fields import JSONField, ArrayField
from django.core.management.base import BaseCommand
from django.db.models import IntegerField, BigIntegerField, BinaryField, \
    CharField, TextField, DateField, TimeField, SmallIntegerField, \
    PositiveIntegerField, PositiveSmallIntegerField, DateTimeField, \
    NullBooleanField, BooleanField, FilePathField, FloatField, SlugField, \
    URLField, UUIDField, AutoField, ImageField, ForeignKey, \
    GenericIPAddressField, FileField
from django.template.loader import render_to_string
from django.utils.safestring import mark_safe
from django.utils.text import capfirst
from django.utils.timezone import now


class Command(BaseCommand):
    label = 'label'
    missing_args_message = "Enter at least one %s." % label

    def add_arguments(self, parser):
        parser.add_argument('args', metavar=self.label, nargs='+')
        parser.add_argument('--package', default='models')

    def handle(self, *labels, **options):
        print('\n'.join(go_flush(labels, package=options['package'])))


arrtypes = {
    'pq.Int64Array': 'int64',
    'pq.StringArray': 'string',
}


class FieldWrapper:
    def __init__(self, f, labels):
        self.primary_key = f.primary_key
        self.attname = f.attname
        self.column = f.column
        self.null = f.null
        self.has_indexes = f.db_index or f.unique or f.primary_key

        self.is_comparable = isinstance(f, (
            DateField,
            DateTimeField,
            FloatField,
            IntegerField,
        ))

        self.orig_name = f.__class__.__name__
        self.camelcased_attname = to_camelcase(f.attname)
        self.gotype, self.type_import = go_type(f)
        if '_' in self.gotype:
            self.gotype = to_camelcase(self.gotype)
        self.is_pointer = self.gotype.startswith('*')
        self.gotype_nopointer = self.gotype.lstrip('*')

        self.is_fk = False
        self.is_same_app_fk = False
        self.rel_classname = False
        if isinstance(f, ForeignKey):
            self.is_same_app_fk = f.model._meta.app_label in labels
            self.rel_classname = f.related_model.__name__
            self.one_to_one = f.one_to_one
        self.camelcased_column = to_camelcase(f.column)

        t, _ = go_type(f, produce_pk=False)
        self.native_type = t

        self.default = None
        self.orig_default = f.default if f.has_default() else ''
        if f.has_default() and not callable(f.default):
            if isinstance(f.default, str):
                if f.null:
                    self.default = mark_safe('spointer("{}")'.format(f.default))
                else:
                    self.default = mark_safe('"{}"'.format(f.default))
            elif (
                isinstance(f.default, (list, tuple)) and
                f.default and
                isinstance(f.default[0], str)
            ):
                self.default = mark_safe("pq.StringArray{%s}" % ', '.join(
                    '"{}"'.format(x) for x in f.default
                ))
            elif isinstance(f.default, bool):
                if self.default:
                    self.default = 'true'
            elif isinstance(f.default, datetime.time):
                self.default = (
                    f'time.Now().Local().Add('
                    f'time.Hour * time.Duration({f.default.hour}) + '
                    f'time.Minute * time.Duration({f.default.minute}) + '
                    f'time.Second * time.Duration({f.default.second})'
                    f')'
                )
            else:
                self.default = f.default
        elif getattr(f, 'auto_now_add', False):
            self.orig_default = 'auto_now_add'
            self.default = 'time.Now()'
        elif getattr(f, 'auto_now', False) or f.default is now:
            self.orig_default = 'auto_now'
            self.default = 'time.Now()'

        self.maybecomment = ''
        if self.gotype.endswith('interface{}'):
            self.maybecomment += ' // type: %s' % self.orig_name
        if self.orig_default:
            self.maybecomment += ' // default value: %s' % self.orig_default

        self.goarrtype = arrtypes.get(self.gotype_nopointer, '')


def go_flush(labels, package):
    result = []

    imports = {
        "database/sql",
        "fmt",
        "log",
        "github.com/lib/pq",
        "github.com/pkg/errors",
        "github.com/tada-team/lorm",
        "github.com/tada-team/lorm/op",
    }

    for label in labels:
        for m in django.apps.apps.get_models(
            include_auto_created=True,
        ):
            meta = m._meta
            if meta.app_label != label:
                continue

            fields = []
            pk_field = None
            new_pk_func = ''
            for f in meta.get_fields():
                if hasattr(f, 'attname') and not hasattr(f, 'm2m_column_name'):
                    fw = FieldWrapper(f, labels)
                    if getattr(f, 'primary_key', None):
                        pk_field = fw
                        if isinstance(f, UUIDField):
                            new_pk_func = 'uuid.New().String()'
                            imports.add('github.com/google/uuid')
                    fields.append(fw)
            assert pk_field

            for fw in fields:
                if fw.type_import:
                    imports.add(fw.type_import)

            fields.sort(key=lambda f: not f.primary_key)

            non_pk_fields = [fw for fw in fields if not fw.primary_key]
            model_name = m.__name__
            model_name = to_camelcase(model_name)
            s = render_to_string('lorm_exporter/model.go.html', {
                'new_pk_func': new_pk_func,
                'model_name': model_name,
                'table_name': meta.db_table,
                'pk_field': pk_field,
                'all_fields': fields,
                'update_set': ', '.join(
                    '{} = ${}'.format(f.column, i)  # 1 = pk
                    for i, f in enumerate(non_pk_fields, start=1)
                ),
                'insert_fields': ', '.join(f.column for f in non_pk_fields),
                'insert_mask': ', '.join(
                    '${}'.format(i)
                    for i, _ in enumerate(non_pk_fields, start=1)
                ),
                'non_pk_fieldslist': mark_safe(', '.join(
                    'row.{}'.format(
                        fw.camelcased_attname,
                    ) for fw in non_pk_fields
                )),
                'intermediate_table': all(
                    fw.rel_classname
                    for fw in non_pk_fields
                )
            })
            result.append(re.sub('\n{3,}', '\n\n', s))

    if imports:
        imports_stmts = ['import (']
        for imp in imports:
            imports_stmts.append('\t"%s"' % imp)
        imports_stmts.append(')')
        imports_stmts.append('')
        result = imports_stmts + result

    result = ['package ' + package, ''] + result

    return result


def pk(model):
    return model.__name__ + 'Pk'


def go_type(field, *, produce_pk=True):
    # TODO: CommaSeparatedIntegerField
    # TODO: DurationField
    prefix = ''
    if field.null:
        prefix = '*'
    t = 'interface{}'
    type_import = None
    if field.primary_key and produce_pk:
        t = pk(field.model)
    elif (
        isinstance(field, ForeignKey)
        # and field.model._meta.app_label == field.related_model._meta.app_label
    ):
        t = pk(field.related_model)
    elif isinstance(field, UUIDField):
        t = 'string'
    elif isinstance(field, GenericIPAddressField):
        t = 'string'
    elif isinstance(field, ArrayField):
        if isinstance(field.base_field, BigIntegerField):
            t = 'pq.Int64Array'
        elif isinstance(field.base_field, CharField):
            t = 'pq.StringArray'
        elif isinstance(field.base_field, UUIDField):
            t = 'string'
        else:
            raise Exception(f'base field not found for {field.base_field}')
    elif isinstance(field, JSONField):
        t = '[]byte'
    elif isinstance(field, BigIntegerField):
        t = 'int64'
    elif isinstance(field, SmallIntegerField):
        t = 'int16'
    elif isinstance(field, PositiveIntegerField):
        t = 'uint'
    elif isinstance(field, PositiveSmallIntegerField):
        t = 'uint16'
    elif isinstance(field, (IntegerField, AutoField)):
        t = 'int'
    elif isinstance(field, FloatField):
        t = 'float'
    elif isinstance(field, BinaryField):
        t = '[]byte'
    elif isinstance(field, (NullBooleanField, BooleanField)):
        t = 'bool'
    elif isinstance(field, (
        CharField,
        TextField,
        FilePathField,
        SlugField,
        URLField,
        ImageField,
        FileField
    )):
        t = 'string'
    elif isinstance(field, (DateField, TimeField, DateTimeField)):
        t = 'time.Time'
        type_import = 'time'
    return prefix + t, type_import


def to_camelcase(s):
    return ''.join(
        capfirst(word) if word[0].upper() != word[0] else word
        for word in s.split('_')
    )
