import sys


def _patch_django_context_copy_for_py314():
    if sys.version_info < (3, 14):
        return
    try:
        from django.template.context import BaseContext
    except Exception:
        return

    original_new = BaseContext.__new__

    def _base_context_copy(self):
        duplicate = original_new(BaseContext)
        duplicate.dicts = self.dicts[:]
        return duplicate

    BaseContext.__copy__ = _base_context_copy


_patch_django_context_copy_for_py314()
