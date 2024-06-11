from datetime import date
from re import match

import grpc
import pytest
from sqlalchemy.sql import func

from couchers import errors
from couchers.db import session_scope
from couchers.models import Cluster, EventOccurrence, UserSession
from couchers.sql import couchers_select as select
from couchers.utils import Timestamp_from_datetime, now, parse_date, timedelta
from proto import admin_pb2, events_pb2
from tests.test_communities import create_community
from tests.test_fixtures import (  # noqa
    db,
    email_fields,
    events_session,
    generate_user,
    get_user_id_and_token,
    mock_notification_email,
    push_collector,
    real_admin_session,
    testconfig,
)


@pytest.fixture(autouse=True)
def _(testconfig):
    pass


def test_access_by_normal_user(db):
    with session_scope():
        normal_user, normal_token = generate_user()

        with real_admin_session(normal_token) as api:
            # all requests to the admin servicer should break when done by a non-super_user
            with pytest.raises(grpc.RpcError) as e:
                api.GetUserDetails(
                    admin_pb2.GetUserDetailsReq(
                        user=str(normal_user.id),
                    )
                )
            assert e.value.code() == grpc.StatusCode.PERMISSION_DENIED


def test_GetUserDetails(db):
    with session_scope():
        super_user, super_token = generate_user(is_superuser=True)
        normal_user, normal_token = generate_user()

        with real_admin_session(super_token) as api:
            res = api.GetUserDetails(admin_pb2.GetUserDetailsReq(user=str(normal_user.id)))
        assert res.user_id == normal_user.id
        assert res.username == normal_user.username
        assert res.email == normal_user.email
        assert res.gender == normal_user.gender
        assert parse_date(res.birthdate) == normal_user.birthdate
        assert not res.banned
        assert not res.deleted

        with real_admin_session(super_token) as api:
            res = api.GetUserDetails(admin_pb2.GetUserDetailsReq(user=normal_user.username))
        assert res.user_id == normal_user.id
        assert res.username == normal_user.username
        assert res.email == normal_user.email
        assert res.gender == normal_user.gender
        assert parse_date(res.birthdate) == normal_user.birthdate
        assert not res.banned
        assert not res.deleted

        with real_admin_session(super_token) as api:
            res = api.GetUserDetails(admin_pb2.GetUserDetailsReq(user=normal_user.email))
        assert res.user_id == normal_user.id
        assert res.username == normal_user.username
        assert res.email == normal_user.email
        assert res.gender == normal_user.gender
        assert parse_date(res.birthdate) == normal_user.birthdate
        assert not res.banned
        assert not res.deleted


def test_ChangeUserGender(db):
    with session_scope():
        super_user, super_token = generate_user(is_superuser=True)
        normal_user, normal_token = generate_user()

        with real_admin_session(super_token) as api:
            res = api.ChangeUserGender(admin_pb2.ChangeUserGenderReq(user=normal_user.username, gender="Machine"))
        assert res.user_id == normal_user.id
        assert res.username == normal_user.username
        assert res.email == normal_user.email
        assert res.gender == "Machine"
        assert parse_date(res.birthdate) == normal_user.birthdate
        assert not res.banned
        assert not res.deleted


def test_ChangeUserBirthdate(db):
    with session_scope():
        super_user, super_token = generate_user(is_superuser=True)
        normal_user, normal_token = generate_user(birthdate=date(year=2000, month=1, day=1))

        with real_admin_session(super_token) as api:
            res = api.GetUserDetails(admin_pb2.GetUserDetailsReq(user=normal_user.username))
            assert parse_date(res.birthdate) == date(year=2000, month=1, day=1)

            res = api.ChangeUserBirthdate(
                admin_pb2.ChangeUserBirthdateReq(user=normal_user.username, birthdate="1990-05-25")
            )

        assert res.user_id == normal_user.id
        assert res.username == normal_user.username
        assert res.email == normal_user.email
        assert res.birthdate == "1990-05-25"
        assert res.gender == normal_user.gender
        assert not res.banned
        assert not res.deleted


def test_BanUser(db):
    with session_scope():
        super_user, super_token = generate_user(is_superuser=True)
        normal_user, _ = generate_user()
        admin_note = "A good reason"
        utc_regex = r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}\+00:00"
        prefix_regex = rf"\n\[{utc_regex}\] \(id: {super_user.id}, username: {super_user.username}\)"

        with real_admin_session(super_token) as api:
            res = api.BanUser(admin_pb2.BanUserReq(user=normal_user.username, admin_note=admin_note))
        assert res.user_id == normal_user.id
        assert res.username == normal_user.username
        assert res.email == normal_user.email
        assert res.gender == normal_user.gender
        assert parse_date(res.birthdate) == normal_user.birthdate
        assert res.banned
        assert not res.deleted
        assert match(rf"^{prefix_regex} {admin_note}\n$", res.admin_note)


def test_AddAdminNote(db):
    with session_scope():
        super_user, super_token = generate_user(is_superuser=True)
        normal_user, _ = generate_user()
        admin_note1 = "User reported strange behavior"
        admin_note2 = "Insert private information here"
        utc_regex = r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}\+00:00"
        prefix_regex = rf"\n\[{utc_regex}\] \(id: {super_user.id}, username: {super_user.username}\)"

        with real_admin_session(super_token) as api:
            res = api.AddAdminNote(admin_pb2.AddAdminNoteReq(user=normal_user.username, admin_note=admin_note1))
        assert res.user_id == normal_user.id
        assert res.username == normal_user.username
        assert res.email == normal_user.email
        assert res.gender == normal_user.gender
        assert parse_date(res.birthdate) == normal_user.birthdate
        assert not res.banned
        assert not res.deleted
        assert match(rf"^{prefix_regex} {admin_note1}\n$", res.admin_note)

        with real_admin_session(super_token) as api:
            res = api.AddAdminNote(admin_pb2.AddAdminNoteReq(user=normal_user.username, admin_note=admin_note2))
        assert match(rf"^{prefix_regex} {admin_note1}\n{prefix_regex} {admin_note2}\n$", res.admin_note)


def test_DeleteUser(db):
    with session_scope():
        super_user, super_token = generate_user(is_superuser=True)
        normal_user, normal_token = generate_user()

        with real_admin_session(super_token) as api:
            res = api.DeleteUser(admin_pb2.DeleteUserReq(user=normal_user.username))
        assert res.user_id == normal_user.id
        assert res.username == normal_user.username
        assert res.email == normal_user.email
        assert res.gender == normal_user.gender
        assert parse_date(res.birthdate) == normal_user.birthdate
        assert not res.banned
        assert res.deleted


def test_CreateApiKey(db, push_collector):
    with session_scope() as session:
        super_user, super_token = generate_user(is_superuser=True)
        normal_user, normal_token = generate_user()

        assert (
            session.execute(
                select(func.count())
                .select_from(UserSession)
                .where(UserSession.is_api_key == True)
                .where(UserSession.user_id == normal_user.id)
            ).scalar_one()
            == 0
        )

    with mock_notification_email() as mock:
        with real_admin_session(super_token) as api:
            res = api.CreateApiKey(admin_pb2.CreateApiKeyReq(user=normal_user.username))

    mock.assert_called_once()
    e = email_fields(mock)
    assert e.subject == "[TEST] Your API key for Couchers.org"

    with session_scope() as session:
        api_key = session.execute(
            select(UserSession)
            .where(UserSession.is_valid)
            .where(UserSession.is_api_key == True)
            .where(UserSession.user_id == normal_user.id)
        ).scalar_one()

        assert api_key.token in e.plain
        assert api_key.token in e.html

    assert e.recipient == normal_user.email
    assert "api key" in e.subject.lower()
    unique_string = "We've issued you with the following API key:"
    assert unique_string in e.plain
    assert unique_string in e.html
    assert "support@couchers.org" in e.plain
    assert "support@couchers.org" in e.html

    push_collector.assert_user_has_single_matching(
        normal_user.id, title="An API key was created for your account", body="Details were sent to you via email."
    )


VALID_GEOJSON_MULTIPOLYGON = """
    {
      "type": "MultiPolygon",
      "coordinates":
       [
        [
          [
            [
              -73.98114904754641,
              40.7470284264813
            ],
            [
              -73.98314135177611,
              40.73416844413217
            ],
            [
              -74.00538969848634,
              40.734314779027144
            ],
            [
              -74.00479214294432,
              40.75027851544338
            ],
            [
              -73.98114904754641,
              40.7470284264813
            ]
          ]
        ]
      ]
    }
"""

POINT_GEOJSON = """
{ "type": "Point", "coordinates": [100.0, 0.0] }
"""


def test_CreateCommunity_invalid_geojson(db):
    with session_scope():
        super_user, super_token = generate_user(is_superuser=True)
        normal_user, normal_token = generate_user()
        with real_admin_session(super_token) as api:
            with pytest.raises(grpc.RpcError) as e:
                api.CreateCommunity(
                    admin_pb2.CreateCommunityReq(
                        name="test community",
                        slug="test-community",
                        description="community for testing",
                        admin_ids=[],
                        geojson=POINT_GEOJSON,
                    )
                )
            assert e.value.code() == grpc.StatusCode.INVALID_ARGUMENT
            assert e.value.details() == errors.NO_MULTIPOLYGON


def test_CreateCommunity(db):
    with session_scope() as session:
        super_user, super_token = generate_user(is_superuser=True)
        normal_user, normal_token = generate_user()
        with real_admin_session(super_token) as api:
            api.CreateCommunity(
                admin_pb2.CreateCommunityReq(
                    name="test community",
                    slug="test-community",
                    description="community for testing",
                    admin_ids=[],
                    geojson=VALID_GEOJSON_MULTIPOLYGON,
                )
            )
            community = session.execute(select(Cluster).where(Cluster.name == "test community")).scalar_one()
            assert community.description == "community for testing"
            assert community.slug == "test-community"


def test_GetChats(db):
    with session_scope():
        super_user, super_token = generate_user(is_superuser=True)
        normal_user, normal_token = generate_user()

        with real_admin_session(super_token) as api:
            res = api.GetChats(admin_pb2.GetChatsReq(user=normal_user.username))
        assert res.response


def test_badges(db):
    with session_scope():
        super_user, super_token = generate_user(is_superuser=True)
        normal_user, normal_token = generate_user()

        with real_admin_session(super_token) as api:
            # can add a badge
            assert "volunteer" not in api.GetUserDetails(admin_pb2.GetUserDetailsReq(user=normal_user.username)).badges
            res = api.AddBadge(admin_pb2.AddBadgeReq(user=normal_user.username, badge_id="volunteer"))
            # assert "volunteer" in api.GetUserDetails(admin_pb2.GetUserDetailsReq(user=normal_user.username)).badges
            assert "volunteer" in res.badges

            # can't add/edit special tags
            with pytest.raises(grpc.RpcError) as e:
                api.AddBadge(admin_pb2.AddBadgeReq(user=normal_user.username, badge_id="founder"))
            assert e.value.code() == grpc.StatusCode.FAILED_PRECONDITION
            assert e.value.details() == errors.ADMIN_CANNOT_EDIT_BADGE

            # double add badge
            with pytest.raises(grpc.RpcError) as e:
                api.AddBadge(admin_pb2.AddBadgeReq(user=normal_user.username, badge_id="volunteer"))
            assert e.value.code() == grpc.StatusCode.FAILED_PRECONDITION
            assert e.value.details() == errors.USER_ALREADY_HAS_BADGE

            # can remove badge
            assert "volunteer" in api.GetUserDetails(admin_pb2.GetUserDetailsReq(user=normal_user.username)).badges
            res = api.RemoveBadge(admin_pb2.RemoveBadgeReq(user=normal_user.username, badge_id="volunteer"))
            assert "volunteer" not in res.badges

            # not found on user
            with pytest.raises(grpc.RpcError) as e:
                api.RemoveBadge(admin_pb2.RemoveBadgeReq(user=normal_user.username, badge_id="volunteer"))
            assert e.value.code() == grpc.StatusCode.FAILED_PRECONDITION
            assert e.value.details() == errors.USER_DOES_NOT_HAVE_BADGE

            # not found in general
            with pytest.raises(grpc.RpcError) as e:
                api.AddBadge(admin_pb2.AddBadgeReq(user=normal_user.username, badge_id="nonexistentbadge"))
            assert e.value.code() == grpc.StatusCode.NOT_FOUND
            assert e.value.details() == errors.BADGE_NOT_FOUND


def test_DeleteEvent(db):
    super_user, super_token = generate_user(is_superuser=True)
    normal_user, normal_token = generate_user()

    with session_scope() as session:
        create_community(session, 0, 2, "Community", [normal_user], [], None)

    start_time = now() + timedelta(hours=2)
    end_time = start_time + timedelta(hours=3)
    with events_session(normal_token) as api:
        res = api.CreateEvent(
            events_pb2.CreateEventReq(
                title="Dummy Title",
                content="Dummy content.",
                photo_key=None,
                offline_information=events_pb2.OfflineEventInformation(
                    address="Near Null Island",
                    lat=0.1,
                    lng=0.2,
                ),
                start_time=Timestamp_from_datetime(start_time),
                end_time=Timestamp_from_datetime(end_time),
                timezone="UTC",
            )
        )
        event_id = res.event_id
        assert not res.is_deleted

    with session_scope() as session:
        with real_admin_session(super_token) as api:
            api.DeleteEvent(
                admin_pb2.DeleteEventReq(
                    event_id=event_id,
                )
            )
            occurrence = session.get(EventOccurrence, ident=event_id)
            assert occurrence.is_deleted


# community invite feature tested in test_events.py
