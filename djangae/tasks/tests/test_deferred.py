import os

from djangae.contrib import sleuth
from django.db import models
from djangae.tasks.deferred import defer
from djangae.test import TestCase, TaskFailedError


def test_task(*args, **kwargs):
    pass


def assert_cache_wiped(instance):
    field = DeferModelA._meta.get_field("b")
    assert(field.get_cached_value(instance, None) is None)


class DeferModelA(models.Model):
    b = models.ForeignKey("DeferModelB", on_delete=models.CASCADE)

    class Meta:
        app_label = "djangae"


class DeferModelB(models.Model):
    class Meta:
        app_label = "djangae"


class DeferTests(TestCase):
    def test_wipe_related_caches(self):
        b = DeferModelB.objects.create()
        a = DeferModelA.objects.create(b=b)
        a.b  # Make sure we access it

        cache_name = DeferModelA._meta.get_field("b").get_cache_name()
        self.assertTrue(getattr(a, cache_name))

        defer(assert_cache_wiped, a)

        # Should raise an assertion error if the cache existed
        try:
            self.process_task_queues()
        except TaskFailedError as e:
            raise e.original_exception

        # Should not have wiped the cache for us!
        self.assertIsNotNone(getattr(a, cache_name, None))

    def test_queues_task(self):
        initial_count = self.get_task_count()
        defer(test_task)
        self.assertEqual(self.get_task_count(), initial_count + 1)

    def test_task_default_routing(self):
        gae_version = 'demo'
        os.environ['GAE_VERSION'] = gae_version

        with sleuth.watch('google.cloud.tasks_v2.CloudTasksClient.create_task') as _create_task:
            defer(test_task)

            self.assertTrue(_create_task.called)
            routing = _create_task.calls[0].args[2]['app_engine_http_request']['app_engine_routing']
            self.assertFalse('service' in routing)
            self.assertFalse('instance' in routing)
            self.assertEqual(routing['version'], gae_version)

        del os.environ['GAE_VERSION']

    def test_task_routing(self):
        service = 'service123'
        version = 'version456'
        instance = 'instance789'
        os.environ['GAE_VERSION'] = 'demo'

        with sleuth.watch('google.cloud.tasks_v2.CloudTasksClient.create_task') as _create_task:
            defer(test_task, _service=service, _version=version, _instance=instance)

            self.assertTrue(_create_task.called)
            routing = _create_task.calls[0].args[2]['app_engine_http_request']['app_engine_routing']
            self.assertEqual(routing['service'], service)
            self.assertEqual(routing['version'], version)
            self.assertEqual(routing['instance'], instance)

        del os.environ['GAE_VERSION']

    def test_deprecated_target_parameter(self):
        self.assertRaises(UserWarning, defer, test_task, _target='test')
