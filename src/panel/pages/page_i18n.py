"""Page i18n key constants — single source of truth for all page i18n keys.

Centralizes every i18n key used in @register_page decorators so typos are caught
by the runtime validation in PageRegistry (missing keys log a warning at import time).
"""

HOME_TITLE = "app.title"

ACTION_CHAIN_TITLE = "chain.title"
ACTION_CHAIN_DESC = "feature.action_chain.desc"

WORKFLOW_EDITOR_TITLE = "workflow.title"
WORKFLOW_EDITOR_DESC = "feature.workflow_editor.desc"

PLUGIN_TITLE = "plugin.title"
PLUGIN_DESC = "feature.plugin_management.desc"

RECORD_TITLE = "record.title"
RECORD_DESC = "feature.macro_record.desc"

NOTIFICATION_TITLE = "notification.title"
NOTIFICATION_DESC = "feature.notification.desc"

SCHEDULE_TITLE = "schedule.title"
SCHEDULE_DESC = "feature.schedule.desc"

SETTINGS_TITLE = "settings.title"
SETTINGS_DESC = "feature.settings.desc"
