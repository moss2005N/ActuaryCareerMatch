from .greenhouse import GreenhouseSourceAdapter
from .json_feed import JSONFeedSourceAdapter
from .lever import LeverSourceAdapter

ADAPTERS = {
    "greenhouse": GreenhouseSourceAdapter,
    "lever": LeverSourceAdapter,
    "ats_api": JSONFeedSourceAdapter,
    "other_api": JSONFeedSourceAdapter,
}


def adapter_class_for(source):
    return ADAPTERS.get(source.source_type)
