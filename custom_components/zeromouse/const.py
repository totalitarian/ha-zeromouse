"""Constants for the ZeroMouse integration."""

DOMAIN = "zeromouse"

REGION = "eu-central-1"
USER_POOL_ID = "eu-central-1_LS6CKN0t1"
CLIENT_ID = "7pdec0rbivg5hg8u3pke4veg0f"
IDENTITY_POOL_ID = "eu-central-1:2b2f7d40-d6f9-474e-a06b-6441c4059601"
GRAPHQL_ENDPOINT = "https://f36gc6o7jnewxe37dhn3fochza.appsync-api.eu-central-1.amazonaws.com/graphql"
DEVICE_SHADOW_ENDPOINT = "https://kus3g3tct7.execute-api.eu-central-1.amazonaws.com/DEV/"
BUCKET_NAME = "mbr-ptf-images-eu-central-1-dev"

DEFAULT_POLL_INTERVAL = 60  # seconds

# How many recent events to pull per poll when scanning for the latest
# occurrence of each classification. Not user-configurable - this is an
# implementation detail (needs to be large enough to likely include at
# least one of each classification value), not a storage retention
# setting like the old capped-history approach was.
EVENT_FETCH_BATCH_SIZE = 50

# CONFIRMED (not guessed) via an exhaustive paginated search of the
# account's full event history (4800+ events, every page walked via
# nextToken): classification_byNet == "prey" is the real confirmed-prey
# value, and critically, every single "prey" event pairs with
# type == "CAT_ENTRY_DENIED" / "ENTRY_DENIED" (entry was actually
# blocked) - never with "CAT_ENTERED". That pairing is what makes this
# genuinely confirmed rather than another guess.
#
# This also retroactively DISPROVES the earlier 'early'/'undecidable'
# guess: both values were found to occur exclusively alongside
# type == "CAT_ENTERED" (successful entry), meaning they were never
# prey at all - just other shades of routine/inconclusive entries.
#
# Other real values found in the same search, not mapped to anything
# (left as their raw string via EVENT_TYPE_LABELS' fallback):
#   'unset' (1171 occurrences - a large, legitimate category, meaning
#            unclear without further investigation)
#   'free' (21), 'test' (4 - likely debug/QA events)
PREY_CLASSIFICATIONS = {"prey"}

CONF_OWNER_ID = "owner_id"
CONF_DEVICE_ID = "device_id"
CONF_DEVICE_NAME = "device_name"
CONF_REFRESH_TOKEN = "refresh_token"
CONF_POLL_INTERVAL = "poll_interval"
CONF_INCLUDE_EXITS = "include_exits"
DEFAULT_INCLUDE_EXITS = True

HISTORY_SUBDIR = "zeromouse/history"  # under config/www/, so served at /local/zeromouse/history/

# Confirmed directly from the app's own "Events" filter screen - these
# are the actual 5 event categories the app itself uses, not raw API
# strings. Mapping from classification_byNet -> these labels:
#   "out"   -> "Leaving detected"   (confirmed)
#   "clean" -> "No prey detected"   (confirmed)
#   "late"  -> "Inconclusive"       (confirmed via app settings text)
#   "prey"  -> "Prey detected"      (confirmed via exhaustive history
#                                    search - see PREY_CLASSIFICATIONS)
# "Hand detected" has no confirmed classification_byNet mapping yet.
# "early"/"undecidable"/"unset"/"free"/"test" are real values (confirmed
# via the same search) but their app-facing meaning isn't known - shown
# as their raw value rather than guessed.
EVENT_TYPE_LABELS = {
    "out": "Leaving detected",
    "clean": "No prey detected",
    "late": "Inconclusive",
    "prey": "Prey detected",
}
