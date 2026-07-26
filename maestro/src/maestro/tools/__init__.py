"""Generic host capabilities registered into the Runtime after construction.

Nothing here is domain logic: these are the primitives a Skill's
``allowed-tools`` can name.  They are registered from ``bootstrap`` rather than
living under ``runtime/`` so the Runtime core stays capability-agnostic.
"""

from maestro.tools.artifacts import register_artifact_capability
from maestro.tools.datetime_query import register_datetime_capability
from maestro.tools.filesystem import register_filesystem_capabilities
from maestro.tools.shell import register_shell_capability
from maestro.tools.skill_resources import register_skill_resource_capability
from maestro.tools.skill_scripts import register_skill_script_capability

__all__ = [
    "register_artifact_capability",
    "register_datetime_capability",
    "register_filesystem_capabilities",
    "register_shell_capability",
    "register_skill_resource_capability",
    "register_skill_script_capability",
]
