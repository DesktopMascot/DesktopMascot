import configparser
import sys
from pathlib import Path


def get_app_directory():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent

    return Path(__file__).resolve().parent


CONFIG_FILE = get_app_directory() / "mascot.conf"


defaults = {
    "Timing": {
        "sit_before_walk_min": "10",
        "sit_before_walk_max": "15",

        "walk_duration_min": "5",
        "walk_duration_max": "8",
        "walk_speed": "2.0",

        "sit_after_walk_min": "10",
        "sit_after_walk_max": "15",

        "rest_min": "10",
        "rest_max": "15",

        "disable_breathing": "false",
    },

    "Network": {
        "chat_url": "http://127.0.0.1/chat_api",
        "event_url": "http://127.0.0.1/event_api",
        "event_poll": "0",
        "ignore_ssl_errors": "false",
        "socks_proxy": "",
        "connect_timeout": "10",
        "read_timeout": "0",
    },
}


config = configparser.ConfigParser()


def load_config():
    changed = False

    if not CONFIG_FILE.exists():
        config.read_dict(defaults)
        changed = True
    else:
        config.read(
            CONFIG_FILE,
            encoding="utf-8"
        )

        # Migrate the old [AI] section to [Network]
        if config.has_section("AI"):
            if not config.has_section("Network"):
                config.add_section("Network")

            for key, value in config.items("AI"):
                if key == "url":
                    if not config.has_option("Network", "chat_url"):
                        config.set("Network", "chat_url", value)
                elif not config.has_option("Network", key):
                    config.set("Network", key, value)

            config.remove_section("AI")
            changed = True

    # Add any newly introduced settings to an existing configuration.
    for section, values in defaults.items():
        if not config.has_section(section):
            config.add_section(section)
            changed = True

        for key, value in values.items():
            if not config.has_option(section, key):
                config.set(section, key, value)
                changed = True

    if changed:
        with CONFIG_FILE.open(
            "w",
            encoding="utf-8"
        ) as file:
            config.write(file)


load_config()


def get_int(section, key):
    return config.getint(section, key)


def get_float(section, key):
    return config.getfloat(section, key)


def get_bool(section, key):
    return config.getboolean(section, key)


def get_str(section, key):
    return config.get(section, key)


def get_config_file():
    return CONFIG_FILE