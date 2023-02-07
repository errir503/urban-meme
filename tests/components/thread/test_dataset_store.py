"""Test the thread dataset store."""
import pytest
from python_otbr_api.tlv_parser import TLVError

from homeassistant.components.thread import dataset_store
from homeassistant.core import HomeAssistant

from . import DATASET_1, DATASET_2, DATASET_3

from tests.common import flush_store

# Same as DATASET_1, but PAN ID moved to the end
DATASET_1_REORDERED = (
    "0E080000000000010000000300000F35060004001FFFE0020811111111222222220708FDAD70BF"
    "E5AA15DD051000112233445566778899AABBCCDDEEFF030E4F70656E54687265616444656D6F04"
    "10445F2B5CA6F2A93A55CE570A70EFEECB0C0402A0F7F801021234"
)


async def test_add_invalid_dataset(hass: HomeAssistant) -> None:
    """Test adding an invalid dataset."""
    with pytest.raises(TLVError, match="unknown type 222"):
        await dataset_store.async_add_dataset(hass, "source", "DEADBEEF")

    store = await dataset_store.async_get_store(hass)
    assert len(store.datasets) == 0


async def test_add_dataset_twice(hass: HomeAssistant) -> None:
    """Test adding dataset twice does nothing."""
    await dataset_store.async_add_dataset(hass, "source", DATASET_1)

    store = await dataset_store.async_get_store(hass)
    assert len(store.datasets) == 1
    created = list(store.datasets.values())[0].created

    await dataset_store.async_add_dataset(hass, "new_source", DATASET_1)
    assert len(store.datasets) == 1
    assert list(store.datasets.values())[0].created == created


async def test_add_dataset_reordered(hass: HomeAssistant) -> None:
    """Test adding dataset with keys in a different order does nothing."""
    await dataset_store.async_add_dataset(hass, "source", DATASET_1)

    store = await dataset_store.async_get_store(hass)
    assert len(store.datasets) == 1
    created = list(store.datasets.values())[0].created

    await dataset_store.async_add_dataset(hass, "new_source", DATASET_1_REORDERED)
    assert len(store.datasets) == 1
    assert list(store.datasets.values())[0].created == created


async def test_dataset_properties(hass: HomeAssistant) -> None:
    """Test dataset entry properties."""
    datasets = [
        {"source": "Google", "tlv": DATASET_1},
        {"source": "Multipan", "tlv": DATASET_2},
        {"source": "🎅", "tlv": DATASET_3},
    ]

    for dataset in datasets:
        await dataset_store.async_add_dataset(hass, dataset["source"], dataset["tlv"])

    store = await dataset_store.async_get_store(hass)
    for dataset in store.datasets.values():
        if dataset.source == "Google":
            dataset_1 = dataset
        if dataset.source == "Multipan":
            dataset_2 = dataset
        if dataset.source == "🎅":
            dataset_3 = dataset

    dataset = store.async_get(dataset_1.id)
    assert dataset == dataset_1
    assert dataset.extended_pan_id == "1111111122222222"
    assert dataset.network_name == "OpenThreadDemo"
    assert dataset.pan_id == "1234"

    dataset = store.async_get(dataset_2.id)
    assert dataset == dataset_2
    assert dataset.extended_pan_id == "1111111122222222"
    assert dataset.network_name == "HomeAssistant!"
    assert dataset.pan_id == "1234"

    dataset = store.async_get(dataset_3.id)
    assert dataset == dataset_3
    assert dataset.extended_pan_id == "1111111122222222"
    assert dataset.network_name == "~🐣🐥🐤~"
    assert dataset.pan_id == "1234"


async def test_load_datasets(hass: HomeAssistant) -> None:
    """Make sure that we can load/save data correctly."""

    datasets = [
        {
            "source": "Google",
            "tlv": DATASET_1,
        },
        {
            "source": "Multipan",
            "tlv": DATASET_2,
        },
        {
            "source": "🎅",
            "tlv": DATASET_3,
        },
    ]

    store1 = await dataset_store.async_get_store(hass)
    for dataset in datasets:
        store1.async_add(dataset["source"], dataset["tlv"])
    assert len(store1.datasets) == 3

    for dataset in store1.datasets.values():
        if dataset.source == "Google":
            dataset_1_store_1 = dataset
        if dataset.source == "Multipan":
            dataset_2_store_1 = dataset
        if dataset.source == "🎅":
            dataset_3_store_1 = dataset

    assert store1.preferred_dataset == dataset_1_store_1.id

    store2 = dataset_store.DatasetStore(hass)
    await flush_store(store1._store)
    await store2.async_load()

    assert len(store2.datasets) == 3

    for dataset in store2.datasets.values():
        if dataset.source == "Google":
            dataset_1_store_2 = dataset
        if dataset.source == "Multipan":
            dataset_2_store_2 = dataset
        if dataset.source == "🎅":
            dataset_3_store_2 = dataset

    assert list(store1.datasets) == list(store2.datasets)

    assert dataset_1_store_1 == dataset_1_store_2
    assert dataset_2_store_1 == dataset_2_store_2
    assert dataset_3_store_1 == dataset_3_store_2


async def test_loading_datasets_from_storage(hass: HomeAssistant, hass_storage) -> None:
    """Test loading stored datasets on start."""
    hass_storage[dataset_store.STORAGE_KEY] = {
        "version": dataset_store.STORAGE_VERSION_MAJOR,
        "minor_version": dataset_store.STORAGE_VERSION_MINOR,
        "data": {
            "datasets": [
                {
                    "created": "2023-02-02T09:41:13.746514+00:00",
                    "id": "id1",
                    "source": "source_1",
                    "tlv": "DATASET_1",
                },
                {
                    "created": "2023-02-02T09:41:13.746514+00:00",
                    "id": "id2",
                    "source": "source_2",
                    "tlv": "DATASET_2",
                },
                {
                    "created": "2023-02-02T09:41:13.746514+00:00",
                    "id": "id3",
                    "source": "source_3",
                    "tlv": "DATASET_3",
                },
            ],
            "preferred_dataset": "id1",
        },
    }

    store = await dataset_store.async_get_store(hass)
    assert len(store.datasets) == 3
    assert store.preferred_dataset == "id1"
