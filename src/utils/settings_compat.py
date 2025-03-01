"""Compatibility layer for pydantic settings"""

try:
    # Try importing from pydantic_settings (newer versions)
    from pydantic_settings import BaseSettings, SettingsConfigDict
except ImportError:
    # Fallback to old pydantic approach
    from pydantic import BaseSettings
    try:
        from pydantic import model_config as SettingsConfigDict  # v2
    except ImportError:
        # Very old pydantic version
        SettingsConfigDict = dict
        # Set a class-level attribute for config
        def _settings_config(cls, config_dict):
            cls.Config = type('Config', (), config_dict)
            return cls
        BaseSettings = lambda cls: _settings_config(cls, {})

__all__ = ['BaseSettings', 'SettingsConfigDict']
