"""Curated golden SDK checks against the real bundled Zoom schema corpus.

The focused SDK tests in `test_sdk.py` keep behavior isolated with a tiny
temporary schema tree. This module complements them by sampling the actual
bundled OpenAPI documents that ship with `zoompy`.

These tests are intentionally opinionated. Their job is to pin the public SDK
surface that outside projects are expected to rely on, especially across the
largest endpoint families.
"""

from __future__ import annotations

from pydantic import BaseModel

from zoompy import ZoomClient, __version__


def _build_client() -> ZoomClient:
    """Create a client that can inspect bundled schemas without live auth."""

    return ZoomClient(access_token="test-access-token")


def test_real_schema_sdk_exposes_expected_top_level_namespaces() -> None:
    """Expose well-known endpoint families from the real packaged schemas."""

    client = _build_client()
    try:
        assert "users" in dir(client)
        assert "phone" in dir(client)
        assert "meetings" in dir(client)

        assert callable(client.users.list)
        assert callable(client.users.get)
        assert callable(client.phone.users.get)
        assert callable(client.phone.users.update_profile)
        assert callable(client.phone.call_queues.list)
        assert callable(client.phone.devices.get)
        assert callable(client.rooms.get_profile)
        assert callable(client.rooms.list_rooms)
        assert callable(client.rooms.delete_room)
        assert callable(client.rooms.locations.list)
        assert callable(client.rooms.locations.get_profile)
        assert callable(client.whiteboard.get_whiteboard)
        assert callable(client.whiteboard.update_metadata)
        assert callable(client.whiteboard.projects.list)
        assert callable(client.meetings.update_meeting)
        assert callable(client.chat.channels.get_account)
        assert callable(client.users.list.iter_pages)
        assert callable(client.users.list.iter_all)
        assert callable(client.users.list.paginate)
        assert callable(client.users.get.raw)
        assert not hasattr(client.phone, "call_queue_analytic")
    finally:
        client.close()


def test_real_schema_sdk_exposes_typed_models_for_common_operations() -> None:
    """Build request and response models from the real bundled schemas."""

    client = _build_client()
    try:
        get_user_model = client.users.get.response_model
        create_user_request_model = client.users.create.request_model
        get_phone_user_model = client.phone.users.get.response_model
    finally:
        client.close()

    assert get_user_model is not None
    assert create_user_request_model is not None
    assert get_phone_user_model is not None

    assert issubclass(get_user_model, BaseModel)
    assert issubclass(create_user_request_model, BaseModel)
    assert issubclass(get_phone_user_model, BaseModel)


def test_real_schema_sdk_docstrings_include_operation_metadata() -> None:
    """Keep generated SDK methods understandable in editors and shells."""

    client = _build_client()
    try:
        docstring = client.phone.users.get.__doc__
    finally:
        client.close()

    assert docstring is not None
    assert "Operation ID:" in docstring
    assert "HTTP:" in docstring
    assert "/phone/users/{userId}" in docstring


def test_real_schema_sdk_common_method_names_are_stable() -> None:
    """Pin a few important public method names as a golden SDK contract."""

    client = _build_client()
    try:
        assert client.users.list._operation.operation_id == "users"
        assert client.users.get._operation.operation_id == "user"
        assert client.phone.users.get._operation.operation_id == "phoneUser"
        assert client.phone.users.update_profile._operation.operation_id == (
            "updateUserProfile"
        )
        assert client.phone.devices.get._operation.operation_id == "getADevice"
        assert client.rooms.get_profile._operation.operation_id == "getZRProfile"
        assert client.rooms.locations.get_profile._operation.operation_id == (
            "getZRLocationProfile"
        )
        assert client.rooms.list_rooms._operation.operation_id == "listZoomRooms"
        assert client.chat.channels.get_account._operation.operation_id == (
            "getAccountChannels"
        )
        assert client.whiteboard.update_metadata._operation.operation_id == (
            "UpdateAWhiteboardMetadata"
        )
        assert client.whiteboard.projects.list._operation.operation_id == (
            "Listallprojects"
        )
    finally:
        client.close()


def test_real_schema_sdk_golden_matrix_for_major_families() -> None:
    """Pin a broader set of stable public SDK methods across major families."""

    client = _build_client()
    try:
        matrix = {
            "users.list": client.users.list._operation.operation_id,
            "users.get": client.users.get._operation.operation_id,
            "phone.users.get": client.phone.users.get._operation.operation_id,
            "phone.users.update_profile": (
                client.phone.users.update_profile._operation.operation_id
            ),
            "phone.call_queues.list": (
                client.phone.call_queues.list._operation.operation_id
            ),
            "phone.call_queues.get": (
                client.phone.call_queues.get._operation.operation_id
            ),
            "phone.devices.list": client.phone.devices.list._operation.operation_id,
            "phone.devices.get": client.phone.devices.get._operation.operation_id,
            "meetings.meeting_summaries.list": (
                client.meetings.meeting_summaries.list._operation.operation_id
            ),
            "meetings.update_meeting": (
                client.meetings.update_meeting._operation.operation_id
            ),
            "chat.channels.get": client.chat.channels.get._operation.operation_id,
            "chat.channels.get_account": (
                client.chat.channels.get_account._operation.operation_id
            ),
            "rooms.add_room": client.rooms.add_room._operation.operation_id,
            "rooms.delete_room": client.rooms.delete_room._operation.operation_id,
            "rooms.get_profile": client.rooms.get_profile._operation.operation_id,
            "rooms.list_rooms": client.rooms.list_rooms._operation.operation_id,
            "rooms.update_profile": client.rooms.update_profile._operation.operation_id,
            "rooms.locations.list": (
                client.rooms.locations.list._operation.operation_id
            ),
            "rooms.locations.get_profile": (
                client.rooms.locations.get_profile._operation.operation_id
            ),
            "rooms.locations.update_profile": (
                client.rooms.locations.update_profile._operation.operation_id
            ),
            "scheduler.schedules.get": (
                client.scheduler.schedules.get._operation.operation_id
            ),
            "whiteboard.get_whiteboard": (
                client.whiteboard.get_whiteboard._operation.operation_id
            ),
            "whiteboard.delete_whiteboard": (
                client.whiteboard.delete_whiteboard._operation.operation_id
            ),
            "whiteboard.update_metadata": (
                client.whiteboard.update_metadata._operation.operation_id
            ),
            "whiteboard.projects.list": (
                client.whiteboard.projects.list._operation.operation_id
            ),
            "whiteboard.projects.get": (
                client.whiteboard.projects.get._operation.operation_id
            ),
            "whiteboard.projects.create": (
                client.whiteboard.projects.create._operation.operation_id
            ),
        }
    finally:
        client.close()

    assert matrix == {
        "users.list": "users",
        "users.get": "user",
        "phone.users.get": "phoneUser",
        "phone.users.update_profile": "updateUserProfile",
        "phone.call_queues.list": "listCallQueues",
        "phone.call_queues.get": "getACallQueue",
        "phone.devices.list": "listPhoneDevices",
        "phone.devices.get": "getADevice",
        "meetings.meeting_summaries.list": "Listmeetingsummaries",
        "meetings.update_meeting": "meetingUpdate",
        "chat.channels.get": "getUserLevelChannel",
        "chat.channels.get_account": "getAccountChannels",
        "rooms.add_room": "addARoom",
        "rooms.delete_room": "deleteAZoomRoom",
        "rooms.get_profile": "getZRProfile",
        "rooms.list_rooms": "listZoomRooms",
        "rooms.update_profile": "updateRoomProfile",
        "rooms.locations.list": "listZRLocations",
        "rooms.locations.get_profile": "getZRLocationProfile",
        "rooms.locations.update_profile": "updateZRLocationProfile",
        "scheduler.schedules.get": "get_schedule",
        "whiteboard.get_whiteboard": "GetAWhiteboard",
        "whiteboard.delete_whiteboard": "DeleteAWhiteboard",
        "whiteboard.update_metadata": "UpdateAWhiteboardMetadata",
        "whiteboard.projects.list": "Listallprojects",
        "whiteboard.projects.get": "Getaproject",
        "whiteboard.projects.create": "Createproject",
    }


def test_real_schema_sdk_prefers_clean_aliases_for_noisy_families() -> None:
    """Pin the preferred public aliases on the ugliest real Zoom families.

    The bundled schemas still produce a number of raw fallback names such as
    `get_a_device`, `getaproject`, and `get_zr_profile`. Those fallbacks are
    still useful as escape hatches, but they are not the public shape we want
    people to learn first.

    This test keeps the preferred aliases stable and also proves that the
    fallback spellings still resolve to the same underlying OpenAPI operation.
    That makes refactors safer because we can improve alias generation without
    silently changing which operation a preferred method name calls.
    """

    client = _build_client()
    try:
        alias_pairs = {
            "phone.devices.get": (
                client.phone.devices.get._operation.operation_id,
                client.phone.devices.get_device._operation.operation_id,
            ),
            "phone.call_queues.get": (
                client.phone.call_queues.get._operation.operation_id,
                client.phone.call_queues.get_call_queue._operation.operation_id,
            ),
            "chat.channels.get_account": (
                client.chat.channels.get_account._operation.operation_id,
                client.chat.channels.get_account_channels._operation.operation_id,
            ),
            "rooms.get_profile": (
                client.rooms.get_profile._operation.operation_id,
                client.rooms.get_zr_profile._operation.operation_id,
            ),
            "rooms.locations.get_profile": (
                client.rooms.locations.get_profile._operation.operation_id,
                client.rooms.locations.get_zr_location_profile._operation.operation_id,
            ),
            "whiteboard.get_whiteboard": (
                client.whiteboard.get_whiteboard._operation.operation_id,
                client.whiteboard.get_a_whiteboard._operation.operation_id,
            ),
            "whiteboard.projects.get": (
                client.whiteboard.projects.get._operation.operation_id,
                client.whiteboard.projects.getaproject._operation.operation_id,
            ),
        }
    finally:
        client.close()

    assert alias_pairs == {
        "phone.devices.get": ("getADevice", "getADevice"),
        "phone.call_queues.get": ("getACallQueue", "getACallQueue"),
        "chat.channels.get_account": (
            "getAccountChannels",
            "getAccountChannels",
        ),
        "rooms.get_profile": ("getZRProfile", "getZRProfile"),
        "rooms.locations.get_profile": (
            "getZRLocationProfile",
            "getZRLocationProfile",
        ),
        "whiteboard.get_whiteboard": (
            "GetAWhiteboard",
            "GetAWhiteboard",
        ),
        "whiteboard.projects.get": ("Getaproject", "Getaproject"),
    }


def test_real_schema_sdk_exposes_preferred_aliases_on_noisy_families() -> None:
    """Keep the preferred public surface visible on the ugliest namespaces.

    The SDK still exposes a number of raw generated fallbacks for compatibility
    and discoverability, but outside callers should be able to rely on a
    smaller set of clean aliases first. This test pins that preferred shape.
    """

    client = _build_client()
    try:
        preferred_aliases = {
            "phone.users": {
                "get": hasattr(client.phone.users, "get"),
                "list": hasattr(client.phone.users, "list"),
                "update_profile": hasattr(client.phone.users, "update_profile"),
            },
            "phone.devices": {
                "get": hasattr(client.phone.devices, "get"),
                "list": hasattr(client.phone.devices, "list"),
                "update": hasattr(client.phone.devices, "update"),
                "delete": hasattr(client.phone.devices, "delete"),
                "create": hasattr(client.phone.devices, "create"),
            },
            "chat.channels": {
                "get": hasattr(client.chat.channels, "get"),
                "get_account": hasattr(client.chat.channels, "get_account"),
                "delete_user_level": hasattr(
                    client.chat.channels, "delete_user_level"
                ),
                "update_user_level": hasattr(
                    client.chat.channels, "update_user_level"
                ),
            },
            "rooms": {
                "add_room": hasattr(client.rooms, "add_room"),
                "delete_room": hasattr(client.rooms, "delete_room"),
                "get_profile": hasattr(client.rooms, "get_profile"),
                "list_rooms": hasattr(client.rooms, "list_rooms"),
                "update_profile": hasattr(client.rooms, "update_profile"),
            },
            "whiteboard": {
                "get_whiteboard": hasattr(client.whiteboard, "get_whiteboard"),
                "delete_whiteboard": hasattr(
                    client.whiteboard, "delete_whiteboard"
                ),
                "update_metadata": hasattr(client.whiteboard, "update_metadata"),
            },
            "whiteboard.projects": {
                "get": hasattr(client.whiteboard.projects, "get"),
                "list": hasattr(client.whiteboard.projects, "list"),
                "create": hasattr(client.whiteboard.projects, "create"),
            },
        }
    finally:
        client.close()

    assert preferred_aliases == {
        "phone.users": {
            "get": True,
            "list": True,
            "update_profile": True,
        },
        "phone.devices": {
            "get": True,
            "list": True,
            "update": True,
            "delete": True,
            "create": True,
        },
        "chat.channels": {
            "get": True,
            "get_account": True,
            "delete_user_level": True,
            "update_user_level": True,
        },
        "rooms": {
            "add_room": True,
            "delete_room": True,
            "get_profile": True,
            "list_rooms": True,
            "update_profile": True,
        },
        "whiteboard": {
            "get_whiteboard": True,
            "delete_whiteboard": True,
            "update_metadata": True,
        },
        "whiteboard.projects": {
            "get": True,
            "list": True,
            "create": True,
        },
    }


def test_real_schema_sdk_exposes_typed_models_on_noisy_families() -> None:
    """Pin typed model availability on the most awkward real operations.

    The SDK is supposed to feel like a scripting SDK, not a thin JSON wrapper.
    These assertions keep that promise visible on the messy parts of the Zoom
    surface where it is easiest to regress back toward untyped behavior.
    """

    client = _build_client()
    try:
        model_matrix = {
            "phone.users.get": {
                "response": client.phone.users.get.response_model,
                "request": client.phone.users.get.request_model,
            },
            "phone.devices.get": {
                "response": client.phone.devices.get.response_model,
                "request": client.phone.devices.get.request_model,
            },
            "phone.call_queues.get": {
                "response": client.phone.call_queues.get.response_model,
                "request": client.phone.call_queues.get.request_model,
            },
            "chat.channels.get": {
                "response": client.chat.channels.get.response_model,
                "request": client.chat.channels.get.request_model,
            },
            "chat.channels.get_account": {
                "response": client.chat.channels.get_account.response_model,
                "request": client.chat.channels.get_account.request_model,
            },
            "rooms.get_profile": {
                "response": client.rooms.get_profile.response_model,
                "request": client.rooms.get_profile.request_model,
            },
            "rooms.locations.get_profile": {
                "response": client.rooms.locations.get_profile.response_model,
                "request": client.rooms.locations.get_profile.request_model,
            },
            "whiteboard.get_whiteboard": {
                "response": client.whiteboard.get_whiteboard.response_model,
                "request": client.whiteboard.get_whiteboard.request_model,
            },
            "whiteboard.projects.get": {
                "response": client.whiteboard.projects.get.response_model,
                "request": client.whiteboard.projects.get.request_model,
            },
            "whiteboard.projects.create": {
                "response": client.whiteboard.projects.create.response_model,
                "request": client.whiteboard.projects.create.request_model,
            },
        }
    finally:
        client.close()

    assert model_matrix["phone.users.get"]["response"] is not None
    assert model_matrix["phone.devices.get"]["response"] is not None
    assert model_matrix["phone.call_queues.get"]["response"] is not None
    assert model_matrix["chat.channels.get"]["response"] is not None
    assert model_matrix["chat.channels.get_account"]["response"] is not None
    assert model_matrix["rooms.get_profile"]["response"] is not None
    assert model_matrix["rooms.locations.get_profile"]["response"] is not None
    assert model_matrix["whiteboard.get_whiteboard"]["response"] is not None
    assert model_matrix["whiteboard.projects.get"]["response"] is not None
    assert model_matrix["whiteboard.projects.create"]["response"] is not None
    assert model_matrix["whiteboard.projects.create"]["request"] is not None

    for entry in model_matrix.values():
        response_model = entry["response"]
        request_model = entry["request"]
        if response_model is not None:
            assert issubclass(response_model, BaseModel)
        if request_model is not None:
            assert issubclass(request_model, BaseModel)


def test_real_schema_sdk_keeps_schema_derived_parameter_names() -> None:
    """Require schema-derived snake_case parameter names on noisy methods.

    Generated SDK methods currently accept `**kwargs`, so Python signatures are
    intentionally loose. The stable source of truth is the normalized operation
    metadata behind each method.

    This test pins the path and query parameter names that scripts are expected
    to use. If alias generation or schema normalization changes accidentally,
    these assertions make that break obvious immediately.
    """

    client = _build_client()
    try:
        parameter_matrix = {
            "phone.users.get": {
                "path": [
                    parameter.python_name
                    for parameter in client.phone.users.get._operation.path_parameters
                ],
                "query": [
                    parameter.python_name
                    for parameter in client.phone.users.get._operation.query_parameters
                ],
            },
            "phone.users.update_profile": {
                "path": [
                    parameter.python_name
                    for parameter in (
                        client.phone.users.update_profile._operation.path_parameters
                    )
                ],
                "query": [
                    parameter.python_name
                    for parameter in (
                        client.phone.users.update_profile._operation.query_parameters
                    )
                ],
            },
            "phone.call_queues.get": {
                "path": [
                    parameter.python_name
                    for parameter in (
                        client.phone.call_queues.get._operation.path_parameters
                    )
                ],
                "query": [
                    parameter.python_name
                    for parameter in (
                        client.phone.call_queues.get._operation.query_parameters
                    )
                ],
            },
            "phone.devices.get": {
                "path": [
                    parameter.python_name
                    for parameter in client.phone.devices.get._operation.path_parameters
                ],
                "query": [
                    parameter.python_name
                    for parameter in (
                        client.phone.devices.get._operation.query_parameters
                    )
                ],
            },
            "chat.channels.get_account": {
                "path": [
                    parameter.python_name
                    for parameter in (
                        client.chat.channels.get_account._operation.path_parameters
                    )
                ],
                "query": [
                    parameter.python_name
                    for parameter in (
                        client.chat.channels.get_account._operation.query_parameters
                    )
                ],
            },
            "chat.channels.delete_user_level": {
                "path": [
                    parameter.python_name
                    for parameter in (
                        client.chat.channels.delete_user_level._operation.path_parameters
                    )
                ],
                "query": [
                    parameter.python_name
                    for parameter in (
                        client.chat.channels.delete_user_level._operation.query_parameters
                    )
                ],
            },
            "rooms.get_profile": {
                "path": [
                    parameter.python_name
                    for parameter in client.rooms.get_profile._operation.path_parameters
                ],
                "query": [
                    parameter.python_name
                    for parameter in client.rooms.get_profile._operation.query_parameters
                ],
            },
            "rooms.locations.get_profile": {
                "path": [
                    parameter.python_name
                    for parameter in (
                        client.rooms.locations.get_profile._operation.path_parameters
                    )
                ],
                "query": [
                    parameter.python_name
                    for parameter in (
                        client.rooms.locations.get_profile._operation.query_parameters
                    )
                ],
            },
            "whiteboard.get_whiteboard": {
                "path": [
                    parameter.python_name
                    for parameter in (
                        client.whiteboard.get_whiteboard._operation.path_parameters
                    )
                ],
                "query": [
                    parameter.python_name
                    for parameter in (
                        client.whiteboard.get_whiteboard._operation.query_parameters
                    )
                ],
            },
            "whiteboard.projects.get": {
                "path": [
                    parameter.python_name
                    for parameter in (
                        client.whiteboard.projects.get._operation.path_parameters
                    )
                ],
                "query": [
                    parameter.python_name
                    for parameter in (
                        client.whiteboard.projects.get._operation.query_parameters
                    )
                ],
            },
        }
    finally:
        client.close()

    assert parameter_matrix == {
        "phone.users.get": {"path": ["user_id"], "query": []},
        "phone.users.update_profile": {"path": ["user_id"], "query": []},
        "phone.call_queues.get": {"path": ["call_queue_id"], "query": []},
        "phone.devices.get": {"path": ["device_id"], "query": []},
        "chat.channels.get_account": {
            "path": [],
            "query": ["page_size", "next_page_token"],
        },
        "chat.channels.delete_user_level": {
            "path": ["channel_id"],
            "query": [],
        },
        "rooms.get_profile": {
            "path": ["room_id"],
            "query": ["regenerate_activation_code"],
        },
        "rooms.locations.get_profile": {
            "path": ["location_id"],
            "query": [],
        },
        "whiteboard.get_whiteboard": {
            "path": ["whiteboard_id"],
            "query": [],
        },
        "whiteboard.projects.get": {
            "path": ["project_id"],
            "query": [],
        },
    }


def test_package_exposes_a_stable_version_string() -> None:
    """Expose an explicit package version for outside consumers to pin."""

    assert isinstance(__version__, str)
    assert __version__
