import os
import pytest
import requests
from lxml import etree
from datetime import datetime as dt
from nexusLIMS import harvesters
from nexusLIMS.harvesters import sharepoint_calendar as sc
from nexusLIMS.utils import nexus_req as _nexus_req
from nexusLIMS.harvesters import ReservationEvent
from nexusLIMS.harvesters.sharepoint_calendar import AuthenticationError
from nexusLIMS.db.session_handler import db_query
from nexusLIMS.instruments import instrument_db
from collections import OrderedDict

import warnings

warnings.filterwarnings(
    action='ignore',
    message=r"DeprecationWarning: Using Ntlm()*",
    category=DeprecationWarning)
warnings.filterwarnings(
    'ignore',
    r"Manually creating the cbt stuct from the cert hash will be removed",
    DeprecationWarning)


class TestSharepoint:
    CREDENTIAL_FILE_ABS = os.path.abspath(
        os.path.join(os.path.dirname(__file__),
                     '..',
                     'credentials.ini.example'))
    CREDENTIAL_FILE_REL = os.path.join('..', 'credentials.ini.example')

    @pytest.mark.parametrize('instrument', list(instrument_db.values()),
                             ids=list(instrument_db.keys()))
    def test_downloading_valid_calendars(self, instrument):
        # Handle the two test instruments that we put into the database,
        # which will raise an error because their url values are bogus
        if instrument.name in ['testsurface-CPU_P1111111',
                               'testVDI-VM-JAT-111222']:
            pass
        else:
            if instrument.harvester == "sharepoint_calendar":
                sc.fetch_xml(instrument)

    def test_download_with_date(self):
        doc = etree.fromstring(
            sc.fetch_xml(instrument=instrument_db['FEI-Titan-TEM-635816'],
                         dt_from=dt.fromisoformat('2018-11-13T00:00:00'),
                         dt_to=dt.fromisoformat('2018-11-13T23:59:59')))
        # This day should have one entry:
        assert len(doc.findall('entry')) == 1

    def test_download_date_w_multiple_entries(self):
        # This should return an event by '***REMOVED***' from 1PM to 5PM on 11/20/2019
        doc = etree.fromstring(
            sc.fetch_xml(instrument=instrument_db['FEI-Titan-TEM-635816'],
                         dt_from=dt.fromisoformat('2019-11-20T13:40:20'),
                         dt_to=dt.fromisoformat('2019-11-20T17:30:00'))
        )
        # This day should have one entry (pared down from three):
        assert len(doc.findall('entry')) == 1
        # entry should be user ***REMOVED*** and title "NexusLIMS computer testing"
        assert doc.find('entry/title').text == "NexusLIMS computer testing"
        assert doc.find('entry/link[@title="UserName"]/'
                        'm:inline/feed/entry/content/m:properties/d:UserName',
                        namespaces=doc.nsmap).text == "***REMOVED***"

    def test_downloading_bad_calendar(self):
        with pytest.raises(KeyError):
            sc.fetch_xml('bogus_instr')

    def test_bad_username(self, monkeypatch):
        with monkeypatch.context() as m:
            m.setenv('nexusLIMS_user', 'bad_user')
            with pytest.raises(AuthenticationError):
                sc.fetch_xml(instrument_db['FEI-Titan-TEM-635816'])

    def test_absolute_path_to_credentials(self, monkeypatch):
        from nexusLIMS.harvesters.sharepoint_calendar import get_auth
        with monkeypatch.context() as m:
            # remove environment variable so we get into file processing
            m.delenv('nexusLIMS_user')
            _ = get_auth(self.CREDENTIAL_FILE_ABS)

    def test_relative_path_to_credentials(self, monkeypatch):
        from nexusLIMS.harvesters.sharepoint_calendar import get_auth
        os.chdir(os.path.dirname(__file__))
        with monkeypatch.context() as m:
            # remove environment variable so we get into file processing
            m.delenv('nexusLIMS_user')
            _ = get_auth(self.CREDENTIAL_FILE_REL)

    def test_bad_path_to_credentials(self, monkeypatch):
        from nexusLIMS.harvesters.sharepoint_calendar import get_auth
        with monkeypatch.context() as m:
            # remove environment variable so we get into file processing
            m.delenv('nexusLIMS_user')
            cred_file = os.path.join('bogus_credentials.ini')
            with pytest.raises(AuthenticationError):
                _ = get_auth(cred_file)

    def test_bad_request_response(self, monkeypatch):
        with monkeypatch.context() as m:
            class MockResponse(object):
                def __init__(self):
                    self.status_code = 404

            def mock_get(url, auth, verify):
                return MockResponse()

            # User bad username so we don't get a valid response or lock miclims
            m.setenv('nexusLIMS_user', 'bad_user')

            # use monkeypatch to use our version of get for requests that
            # always returns a 404
            monkeypatch.setattr(requests, 'get', mock_get)
            with pytest.raises(requests.exceptions.ConnectionError):
                sc.fetch_xml(instrument_db['FEI-Titan-TEM-635816'])

    def test_fetch_xml_instrument_none(self, monkeypatch):
        with monkeypatch.context() as m:
            # use bad username so we don't get a response or lock miclims
            m.setenv('nexusLIMS_user', 'bad_user')
            with pytest.raises(AuthenticationError):
                sc.fetch_xml(instrument_db['FEI-Titan-TEM-635816'])

    def test_fetch_xml_instrument_bogus(self, monkeypatch):
        with monkeypatch.context() as m:
            # use bad username so we don't get a response or lock miclims
            m.setenv('nexusLIMS_user', 'bad_user')
            with pytest.raises(ValueError):
                sc.fetch_xml(instrument=5)

    def test_fetch_xml_only_dt_from(self):
        # at the time of writing this code (2021-09-13), there were 278 records
        # on the Titan STEM after Jan 1. 2020, which should only increase
        # over time
        xml = sc.fetch_xml(instrument_db['FEI-Titan-STEM-630901'],
                           dt_from=dt.fromisoformat('2020-01-01T00:00:00'))
        doc = etree.fromstring(xml)
        assert len(doc.findall('entry')) >= 278

    def test_fetch_xml_only_dt_to(self):
        # There are nine events prior to April 1, 2019 on the Titan STEM
        xml = sc.fetch_xml(instrument_db['FEI-Titan-STEM-630901'],
                           dt_to=dt.fromisoformat('2019-04-01T00:00:00'))
        doc = etree.fromstring(xml)
        assert len(doc.findall('entry')) == 9

    def test_sharepoint_fetch_xml_reservation_event(self):
        xml = \
            sc.fetch_xml(instrument=instrument_db['FEI-Titan-TEM-635816'],
                         dt_from=dt.fromisoformat('2018-11-13T00:00:00'),
                         dt_to=dt.fromisoformat('2018-11-13T23:59:59'))
        cal_event = sc.res_event_from_xml(xml)
        assert cal_event.experiment_title == '***REMOVED***'
        assert cal_event.internal_id == '470'
        assert cal_event.username == '***REMOVED***'
        assert cal_event.start_time == dt.fromisoformat(
            '2018-11-13T09:00:00-05:00')

    def test_sharepoint_fetch_xml_reservation_event_no_entry(self):
        # tests when there is no matching event found
        xml = \
            sc.fetch_xml(instrument=instrument_db['FEI-Titan-TEM-635816'],
                         dt_from=dt.fromisoformat('2010-01-01T00:00:00'),
                         dt_to=dt.fromisoformat('2010-01-01T00:00:01'))
        cal_event = sc.res_event_from_xml(xml)
        assert cal_event.experiment_title is None
        assert cal_event.instrument.name == 'FEI-Titan-TEM-635816'
        assert cal_event.username is None

    def test_sharepoint_res_event_from_session(self):
        from nexusLIMS.db.session_handler import Session
        s = Session(session_identifier="test_identifier",
                    instrument=instrument_db['FEI-Titan-TEM-635816'],
                    dt_from=dt.fromisoformat('2018-11-13T00:00:00'),
                    dt_to=dt.fromisoformat('2018-11-13T23:59:59'),
                    user='unused')
        res_event = sc.res_event_from_session(s)
        assert res_event.experiment_title == '***REMOVED***'
        assert res_event.instrument.name == 'FEI-Titan-TEM-635816'
        assert res_event.internal_id == '470'
        assert res_event.username == '***REMOVED***'
        assert res_event.start_time == dt.fromisoformat(
            '2018-11-13T09:00:00-05:00')

    def test_reservation_event_repr(self):
        s = dt(2020, 8, 20, 12, 0, 0)
        e = dt(2020, 8, 20, 16, 0, 40)
        c = ReservationEvent(experiment_title='Test event',
                             instrument=instrument_db['FEI-Titan-TEM-635816'],
                             last_updated=dt.now(), username='***REMOVED***',
                             created_by='***REMOVED***', start_time=s, end_time=e,
                             reservation_type='category',
                             experiment_purpose='purpose',
                             sample_details='sample details',
                             project_id='projectID',
                             internal_id='999')
        assert c.__repr__() == 'Event for ***REMOVED*** on FEI-Titan-TEM-635816 from ' \
                               '2020-08-20T12:00:00 to 2020-08-20T16:00:40'

        c = ReservationEvent()
        assert c.__repr__() == 'No matching calendar event'

        c = ReservationEvent(instrument=instrument_db['FEI-Titan-TEM-635816'])
        assert c.__repr__() == 'No matching calendar event for ' \
                               'FEI-Titan-TEM-635816'

    def test_dump_calendars(self, tmp_path):
        from nexusLIMS.harvesters.sharepoint_calendar import dump_calendars
        f = os.path.join(tmp_path, 'cal_output.xml')
        dump_calendars(instrument='FEI-Titan-TEM-635816', filename=f)
        pass

    def test_division_group_lookup(self):
        from nexusLIMS.harvesters.sharepoint_calendar import get_div_and_group
        div, group = get_div_and_group('***REMOVED***')
        assert div == '641'
        assert group == '02'

    def test_get_events_good_date(self):
        from nexusLIMS.harvesters.sharepoint_calendar import get_events
        events_1 = get_events(instrument='FEI-Titan-TEM-635816',
                              dt_from=dt.fromisoformat('2019-03-13T08:00:00'),
                              dt_to=dt.fromisoformat('2019-03-13T16:00:00'))
        assert events_1.username is None
        assert events_1.created_by == '***REMOVED***'
        assert events_1.experiment_title == '***REMOVED***'

    def test_basic_auth(self):
        from nexusLIMS.harvesters.sharepoint_calendar import get_auth
        res = get_auth(basic=True)
        assert isinstance(res, tuple)

    def test_get_sharepoint_date_string(self):
        date_str = sc._get_sharepoint_date_string(
            dt(year=2020, month=6, day=29, hour=1, minute=23, second=48))
        assert date_str == '2020-06-28T21:23:48'

    def test_get_sharepoint_date_string_no_env_var(self, monkeypatch):
        with monkeypatch.context() as m:
            # remove environment variable to test error raising
            m.delenv('nexusLIMS_timezone')
            with pytest.raises(EnvironmentError):
                sc._get_sharepoint_date_string(dt.now())

    def test_get_sharepoint_tz(self, monkeypatch):
        assert sc._get_sharepoint_tz() in ['America/New_York',
                                           'America/Chicago',
                                           'America/Denver',
                                           'America/Los_Angeles',
                                           'Pacific/Honolulu']

        # Create a fake response object that will have the right xml (like
        # would be returned if the server were in different time zones)
        class MockResponse(object):
            def __init__(self, text):
                self.text = \
                    """<?xml version="1.0" encoding="utf-8"?>
<feed xml:base="https://***REMOVED***/Div/msed/MSED-MMF/_api/"
      xmlns="http://www.w3.org/2005/Atom"
      xmlns:d="http://schemas.microsoft.com/ado/2007/08/dataservices"
      xmlns:m="http://schemas.microsoft.com/ado/2007/08/dataservices/metadata"
      xmlns:georss="http://www.georss.org/georss"
      xmlns:gml="http://www.opengis.net/gml">
""" + text + "</feed>"

        def mock_get_et(url, req):
            return MockResponse(text="""
            <content type="application/xml">
                <m:properties>
                    <d:Description>(UTC-05:00) Eastern Time (US and 
                    Canada)</d:Description>
                    <d:Id m:type="Edm.Int32">11</d:Id>
                    <d:Information m:type="SP.TimeZoneInformation">
                        <d:Bias m:type="Edm.Int32">360</d:Bias>
                        <d:DaylightBias m:type="Edm.Int32">-60</d:DaylightBias>
                        <d:StandardBias m:type="Edm.Int32">0</d:StandardBias>
                    </d:Information>
                </m:properties>
            </content>
            """)

        def mock_get_ct(url, req):
            return MockResponse(text="""
            <content type="application/xml">
                <m:properties>
                    <d:Description>(UTC-06:00) Central Time (US and 
                    Canada)</d:Description>
                    <d:Id m:type="Edm.Int32">11</d:Id>
                    <d:Information m:type="SP.TimeZoneInformation">
                        <d:Bias m:type="Edm.Int32">360</d:Bias>
                        <d:DaylightBias m:type="Edm.Int32">-60</d:DaylightBias>
                        <d:StandardBias m:type="Edm.Int32">0</d:StandardBias>
                    </d:Information>
                </m:properties>
            </content>
            """)

        def mock_get_mt(url, req):
            return MockResponse(text="""
            <content type="application/xml">
                <m:properties>
                    <d:Description>(UTC-07:00) Mountain Time (US and 
                    Canada)</d:Description>
                    <d:Id m:type="Edm.Int32">12</d:Id>
                    <d:Information m:type="SP.TimeZoneInformation">
                        <d:Bias m:type="Edm.Int32">420</d:Bias>
                        <d:DaylightBias m:type="Edm.Int32">-60</d:DaylightBias>
                        <d:StandardBias m:type="Edm.Int32">0</d:StandardBias>
                    </d:Information>
            </m:properties>
            </content>
            """)

        def mock_get_pt(url, req):
            return MockResponse(text="""
            <content type="application/xml">
                <m:properties>
                    <d:Description>(UTC-08:00) Pacific Time (US and 
                    Canada)</d:Description>
                    <d:Id m:type="Edm.Int32">13</d:Id>
                    <d:Information m:type="SP.TimeZoneInformation">
                        <d:Bias m:type="Edm.Int32">480</d:Bias>
                        <d:DaylightBias m:type="Edm.Int32">-60</d:DaylightBias>
                        <d:StandardBias m:type="Edm.Int32">0</d:StandardBias>
                    </d:Information>
                </m:properties>
            </content>
            """)

        def mock_get_ht(url, req):
            return MockResponse(text="""
            <content type="application/xml">
                <m:properties>
                    <d:Description>(UTC-10:00) Hawaii</d:Description>
                    <d:Id m:type="Edm.Int32">15</d:Id>
                    <d:Information m:type="SP.TimeZoneInformation">
                        <d:Bias m:type="Edm.Int32">600</d:Bias>
                        <d:DaylightBias m:type="Edm.Int32">-60</d:DaylightBias>
                        <d:StandardBias m:type="Edm.Int32">0</d:StandardBias>
                    </d:Information>
                </m:properties>
            </content>
            """)

        monkeypatch.setattr(sc, '_nexus_req', mock_get_et)
        assert sc._get_sharepoint_tz() == 'America/New_York'
        monkeypatch.setattr(sc, '_nexus_req', mock_get_ct)
        assert sc._get_sharepoint_tz() == 'America/Chicago'
        monkeypatch.setattr(sc, '_nexus_req', mock_get_mt)
        assert sc._get_sharepoint_tz() == 'America/Denver'
        monkeypatch.setattr(sc, '_nexus_req', mock_get_pt)
        assert sc._get_sharepoint_tz() == 'America/Los_Angeles'
        monkeypatch.setattr(sc, '_nexus_req', mock_get_ht)
        assert sc._get_sharepoint_tz() == 'Pacific/Honolulu'


class TestNemoIntegration:
    @pytest.fixture
    def nemo_connector(self):
        """
        A NemoConnector instance that can be used for valid tests
        """
        assert 'NEMO_address_1' in os.environ
        assert 'NEMO_token_1' in os.environ
        from nexusLIMS.harvesters.nemo import NemoConnector
        return NemoConnector(os.environ['NEMO_address_1'],
                             os.environ['NEMO_token_1'])

    @pytest.fixture
    def bogus_nemo_connector_url(self):
        """
        A NemoConnector with a bad URL and token that should fail
        """
        from nexusLIMS.harvesters.nemo import NemoConnector
        return NemoConnector("https://a_url_that_doesnt_exist/",
                             "notneeded")

    @pytest.fixture
    def bogus_nemo_connector_token(self):
        """
        A NemoConnector with a bad URL and token that should fail
        """
        from nexusLIMS.harvesters.nemo import NemoConnector
        return NemoConnector(os.environ['NEMO_address_1'],
                             "badtokenvalue")

    def test_nemo_connector_repr(self, nemo_connector):
        assert str(nemo_connector) == f"Connection to NEMO API at " \
                                      f"{os.environ['NEMO_address_1']}"

    def test_nemo_multiple_harvesters_enabled(self, monkeypatch):
        monkeypatch.setenv("NEMO_address_2", "https://nemo.address.com/api/")
        monkeypatch.setenv("NEMO_token_2", "sometokenvalue")

        from nexusLIMS.harvesters import nemo
        assert len(nemo.get_harvesters_enabled()) == 2
        assert str(nemo.get_harvesters_enabled()[1]) == \
            f"Connection to NEMO API at " \
            f"{os.environ['NEMO_address_2']}"

    def test_nemo_harvesters_enabled(self):
        from nexusLIMS.harvesters import nemo
        assert len(nemo.get_harvesters_enabled()) == 1
        assert str(nemo.get_harvesters_enabled()[0]) == \
            f"Connection to NEMO API at " \
            f"{os.environ['NEMO_address_1']}"

    def test_getting_nemo_data(self):
        from nexusLIMS.utils import nexus_req
        from urllib.parse import urljoin
        from requests import get as _get
        r = nexus_req(url=urljoin(os.environ['NEMO_address_1'],
                                  'api/reservations'),
                      fn=_get, token_auth=os.environ['NEMO_token_1'])

    @pytest.mark.parametrize("test_user_id_input,"
                             "expected_usernames",
                             [(3, ["***REMOVED***"]),
                              ([2, 3, 4], ["***REMOVED***", "***REMOVED***", "***REMOVED***"]),
                              (-1, [])])
    def test_get_users(self, nemo_connector, test_user_id_input,
                       expected_usernames):
        users = nemo_connector.get_users(user_id=test_user_id_input)
        # test for the username in each entry, and compare as a set so it's an
        # unordered and deduplicated comparison
        assert set([u['username'] for u in users]) == set(expected_usernames)

    @pytest.mark.parametrize("test_username_input,"
                             "expected_usernames",
                             [('***REMOVED***', ["***REMOVED***"]),
                              (['***REMOVED***', '***REMOVED***', '***REMOVED***'],
                               ["***REMOVED***", "***REMOVED***", "***REMOVED***"]),
                              ('ernst_ruska', [])])
    def test_get_users_by_username(self, nemo_connector,
                                   test_username_input, expected_usernames):
        users = nemo_connector.get_users_by_username(
            username=test_username_input)
        # test for the username in each entry, and compare as a set so it's an
        # unordered and deduplicated comparison
        assert set([u['username'] for u in users]) == set(expected_usernames)

    def test_get_users_memoization(self):
        # to test the memoization of user data, we have to use one instance
        # of NemoConnector rather than a new one from the fixture for each call
        n = harvesters.nemo.NemoConnector(os.environ['NEMO_address_1'],
                                          os.environ['NEMO_token_1'])
        to_test = [(3, ["***REMOVED***"]),
                   ([2, 3, 4], ["***REMOVED***", "***REMOVED***", "***REMOVED***"]),
                   (-1, []),
                   ([2, 3], ["***REMOVED***", "***REMOVED***"]),
                   (2, ["***REMOVED***"])]
        for u_id, expected in to_test:
            users = n.get_users(u_id)
            assert set([u['username'] for u in users]) == set(expected)

    def test_get_users_by_username_memoization(self):
        # to test the memoization of user data, we have to use one instance
        # of NemoConnector rather than a new one from the fixture for each call
        from nexusLIMS.harvesters.nemo import NemoConnector
        n = NemoConnector(os.environ['NEMO_address_1'],
                          os.environ['NEMO_token_1'])
        to_test = [('***REMOVED***', ["***REMOVED***"]),
                   (['***REMOVED***', '***REMOVED***', '***REMOVED***'], ["***REMOVED***", "***REMOVED***", "***REMOVED***"]),
                   ('ernst_ruska', []),
                   (['***REMOVED***', '***REMOVED***'], ['***REMOVED***', '***REMOVED***']),
                   ('***REMOVED***', ['***REMOVED***'])]
        for uname, expected in to_test:
            users = n.get_users_by_username(uname)
            assert set([u['username'] for u in users]) == set(expected)

    def test_get_users_bad_url(self, bogus_nemo_connector_url):
        with pytest.raises(requests.exceptions.ConnectionError):
            bogus_nemo_connector_url.get_users()

    def test_get_users_bad_token(self, bogus_nemo_connector_token):
        with pytest.raises(requests.exceptions.HTTPError) as e:
            bogus_nemo_connector_token.get_users()
        assert "401" in str(e.value)
        assert "Unauthorized" in str(e.value)

    @pytest.mark.parametrize("test_tool_id_input,expected_names",
                             [(1, ["643 Titan (S)TEM (probe corrected)"]),
                              ([1, 2], ["643 Titan (S)TEM (probe corrected)",
                                        "642 JEOL 3010 (strobo)"]),
                              ([1, 2, 3], ["643 Titan (S)TEM (probe corrected)",
                                           "642 JEOL 3010 (strobo)",
                                           "642 Titan"]),
                              (-1, [])])
    def test_get_tools(self, nemo_connector,
                       test_tool_id_input, expected_names):
        tools = nemo_connector.get_tools(test_tool_id_input)
        # test for the tool name in each entry, and compare as a set so it's an
        # unordered and deduplicated comparison
        assert set([t['name'] for t in tools]) == set(expected_names)

    def test_get_tools_memoization(self):
        # to test the memoization of tool data, we have to use one instance
        # of NemoConnector rather than a new one from the fixture for each call
        from nexusLIMS.harvesters.nemo import NemoConnector
        n = NemoConnector(os.environ['NEMO_address_1'],
                          os.environ['NEMO_token_1'])
        to_test = [([1, 2, 3], ["643 Titan (S)TEM (probe corrected)",
                                "642 JEOL 3010 (strobo)",
                                "642 Titan"]),
                   (2, ["642 JEOL 3010 (strobo)"]),
                   ([2, 3], ["642 JEOL 3010 (strobo)",
                             "642 Titan"])]
        for t_id, expected in to_test:
            tools = n.get_tools(t_id)
            assert set([t['name'] for t in tools]) == set(expected)

    @pytest.mark.parametrize("test_proj_id_input,expected_names",
                             [(6, ["610"]),
                              ([3, 4], ["641", "642"]),
                              ([10, 9, 8], ["735", "683", "681"]),
                              (-1, [])])
    def test_get_projects(self, nemo_connector,
                          test_proj_id_input, expected_names):
        proj = nemo_connector.get_projects(test_proj_id_input)
        # test for the project name in each entry, and compare as a set so
        # it's an unordered and deduplicated comparison
        assert set([p['name'] for p in proj]) == set(expected_names)

    def test_get_projects_memoization(self):
        # to test the memoization of project data, we have to use one instance
        # of NemoConnector rather than a new one from the fixture for each call
        from nexusLIMS.harvesters.nemo import NemoConnector
        n = NemoConnector(os.environ['NEMO_address_1'],
                          os.environ['NEMO_token_1'])
        to_test = [([10, 9, 8], ["735", "683", "681"]),
                   (10, ["735"]),
                   ([9, 8], ["683", "681"])]
        for p_id, expected in to_test:
            projects = n.get_projects(p_id)
            assert set([p['name'] for p in projects]) == set(expected)

    def test_get_reservations(self, nemo_connector):
        # not sure best way to test this, but defaults should return at least
        # as many dictionaries as were present on the day these tests were
        # written (Sept. 20, 2021)
        defaults = nemo_connector.get_reservations()
        assert len(defaults) > 10
        assert all([key in defaults[0] for key in ['id', 'question_data',
                                                   'creation_time', 'start',
                                                   'end']])
        assert all([isinstance(d, dict) for d in defaults])

        dt_test = dt.fromisoformat('2021-09-15T00:00:00-06:00')
        date_gte = nemo_connector.get_reservations(dt_from=dt_test)
        assert all([dt.fromisoformat(d['start']) >= dt_test for d in date_gte])

        dt_test = dt.fromisoformat('2021-09-17T23:59:59-06:00')
        date_lte = nemo_connector.get_reservations(dt_to=dt_test)
        assert all([dt.fromisoformat(d['end']) <= dt_test for d in date_lte])

        dt_test_from = dt.fromisoformat('2021-09-15T00:00:00-06:00')
        dt_test_to = dt.fromisoformat('2021-09-17T23:59:59-06:00')
        date_both = nemo_connector.get_reservations(dt_from=dt_test_from,
                                                    dt_to=dt_test_to)
        assert all([
            dt.fromisoformat(d['start']) >= dt_test_from and
            dt.fromisoformat(d['end']) <= dt_test_to
            for d in date_both
        ])

        cancelled = nemo_connector.get_reservations(cancelled=True)
        assert all([d['cancelled'] is True for d in cancelled])

        one_tool = nemo_connector.get_reservations(tool_id=2)
        assert all([d['tool']['id'] is 2 for d in one_tool])

        multi_tool = nemo_connector.get_reservations(tool_id=[2, 10])
        assert all([d['tool']['id'] in [2, 10] for d in multi_tool])

    def test_get_usage_events(self, nemo_connector):
        # not sure best way to test this, but defaults should return at least
        # as many dictionaries as were present on the day these tests were
        # written (Sept. 20, 2021)
        defaults = nemo_connector.get_usage_events()
        assert len(defaults) >= 3
        assert all([key in defaults[0] for key in ['id', 'start', 'end',
                                                   'run_data', 'user',
                                                   'operator', 'project',
                                                   'tool']])
        assert all([isinstance(d, dict) for d in defaults])

        dt_test = dt.fromisoformat('2021-09-20T00:00:00-06:00')
        date_gte = nemo_connector.get_usage_events(dt_from=dt_test)
        assert all([dt.fromisoformat(d['start']) >= dt_test for d in date_gte])

        dt_test = dt.fromisoformat('2021-09-13T23:59:59-06:00')
        date_lte = nemo_connector.get_usage_events(dt_to=dt_test)
        assert all([dt.fromisoformat(d['end']) <= dt_test for d in date_lte])

        dt_test_from = dt.fromisoformat('2021-09-13T14:00:00-06:00')
        dt_test_to = dt.fromisoformat('2021-09-20T00:00:00-06:00')
        date_both = nemo_connector.get_usage_events(dt_from=dt_test_from,
                                                    dt_to=dt_test_to)
        assert all([
            dt.fromisoformat(d['start']) >= dt_test_from and
            dt.fromisoformat(d['end']) <= dt_test_to
            for d in date_both
        ])
        assert len(date_both) == 2

        one_tool = nemo_connector.get_usage_events(tool_id=1)
        assert all([d['tool']['id'] is 1 for d in one_tool])

        multi_tool = nemo_connector.get_usage_events(tool_id=[1, 5])
        assert all([d['tool']['id'] in [1, 5] for d in multi_tool])

        username_test = nemo_connector.get_usage_events(user='***REMOVED***')
        assert all([d['user']['id'] == 3 for d in username_test])

        user_id_test = nemo_connector.get_usage_events(user=18)  # a***REMOVED***
        assert all([d['user']['username'] == 'a***REMOVED***' for d in user_id_test])

        dt_test_from = dt.fromisoformat('2021-09-13T16:01:00-06:00')
        dt_test_to = dt.fromisoformat('2021-09-13T16:02:00-06:00')
        multiple_test = nemo_connector.get_usage_events(user=18,
                                                        dt_from=dt_test_from,
                                                        dt_to=dt_test_to,
                                                        tool_id=1)
        # should return one usage event
        assert len(multiple_test) == 1
        assert multiple_test[0]['user']['username'] == 'a***REMOVED***'

        # test event_id
        one_event = nemo_connector.get_usage_events(event_id=3)
        assert len(one_event) == 1
        assert one_event[0]['user']['username'] == '***REMOVED***'

        multi_events = nemo_connector.get_usage_events(event_id=[3, 4, 5])
        assert len(multi_events) == 3

    @pytest.fixture
    def cleanup_session_log(self):
        # this fixture removes the rows for the usage event added in
        # test_usage_event_to_session_log, so it doesn't mess up future
        # record building tests
        yield None
        db_query('DELETE FROM session_log WHERE session_identifier LIKE ?',
                 ('%usage_events/?id=3%',))

    def test_usage_event_to_session_log(self,
                                        nemo_connector,
                                        cleanup_session_log):
        success_before, results_before = db_query('SELECT * FROM session_log;')
        nemo_connector.write_usage_event_to_session_log(3)
        success_after, results_after = db_query('SELECT * FROM session_log;')
        assert len(results_after) - len(results_before) == 2

        success, results = db_query('SELECT * FROM session_log ORDER BY '
                                    'id_session_log DESC LIMIT 2;')
        # session ids are same:
        assert results[0][1] == results[1][1]
        assert results[0][1].endswith("/api/usage_events/?id=3")
        # record status
        assert results[0][5] == 'TO_BE_BUILT'
        assert results[1][5] == 'TO_BE_BUILT'
        # event type
        assert results[0][4] == 'END'
        assert results[1][4] == 'START'

    def test_usage_event_to_session_log_non_existent_event(self,
                                                           caplog,
                                                           nemo_connector):
        success_before, results_before = db_query('SELECT * FROM session_log;')
        nemo_connector.write_usage_event_to_session_log(0)
        success_after, results_after = db_query('SELECT * FROM session_log;')
        assert 'No usage event with id = 0 was found' in caplog.text
        assert 'WARNING' in caplog.text
        assert len(results_after) == len(results_before)

    def test_usage_event_to_session(self, nemo_connector):
        session = nemo_connector.get_session_from_usage_event(3)
        assert session.dt_from == \
               dt.fromisoformat('2021-09-20T12:02:19.930972-06:00')
        assert session.dt_to == \
               dt.fromisoformat('2021-09-20T13:13:49.123309-06:00')
        assert session.user == '***REMOVED***'
        assert session.instrument == instrument_db['testsurface-CPU_P1111111']

    def test_usage_event_to_session_non_existent_event(self,
                                                       caplog,
                                                       nemo_connector):
        session = nemo_connector.get_session_from_usage_event(0)
        assert 'No usage event with id = 0 was found' in caplog.text
        assert 'WARNING' in caplog.text
        assert session is None

    def test_res_event_from_session(self):
        from nexusLIMS.db.session_handler import Session
        from nexusLIMS.harvesters import nemo
        s = Session('test_matching_reservation',
                    instrument_db['FEI-Titan-TEM-635816_n'],
                    dt.fromisoformat('2021-08-02T15:00:00-06:00'),
                    dt.fromisoformat('2021-08-02T16:00:00-06:00'),
                    user='***REMOVED***')
        res_event = nemo.res_event_from_session(s)
        assert res_event.instrument == instrument_db['FEI-Titan-TEM-635816_n']
        assert res_event.experiment_title == '***REMOVED***'
        assert res_event.experiment_purpose == \
               '***REMOVED*** ***REMOVED*** ' \
               '***REMOVED***.'
        assert res_event.sample_name == "***REMOVED***'s ***REMOVED***"
        assert res_event.project_id is None
        assert res_event.username == '***REMOVED***'
        assert res_event.internal_id == '87'

    def test_res_event_from_session_no_matching_sessions(self):
        from nexusLIMS.db.session_handler import Session
        from nexusLIMS.harvesters import nemo
        s = Session('test_no_reservations',
                    instrument_db['FEI-Titan-TEM-635816_n'],
                    dt.fromisoformat('2021-08-10T15:00:00-06:00'),
                    dt.fromisoformat('2021-08-10T16:00:00-06:00'),
                    user='***REMOVED***')
        res_event = nemo.res_event_from_session(s)
        assert res_event.username == '***REMOVED***'
        assert res_event.start_time == dt.fromisoformat(
            '2021-08-10T15:00:00-06:00')
        assert res_event.end_time == dt.fromisoformat(
            '2021-08-10T16:00:00-06:00')

    def test_res_event_from_session_no_overlapping_sessions(self):
        from nexusLIMS.db.session_handler import Session
        from nexusLIMS.harvesters import nemo
        s = Session('test_no_reservations',
                    instrument_db['FEI-Titan-TEM-635816_n'],
                    dt.fromisoformat('2021-08-05T15:00:00-06:00'),
                    dt.fromisoformat('2021-08-05T16:00:00-06:00'),
                    user='***REMOVED***')
        res_event = nemo.res_event_from_session(s)
        assert res_event.username == '***REMOVED***'
        assert res_event.start_time == dt.fromisoformat(
            '2021-08-05T15:00:00-06:00')
        assert res_event.end_time == dt.fromisoformat(
            '2021-08-05T16:00:00-06:00')

    def test_no_connector_for_session(self):
        from nexusLIMS.db.session_handler import Session
        from nexusLIMS.instruments import Instrument
        from nexusLIMS.harvesters import nemo
        s = Session('test_no_reservations',
                    Instrument(name='Dummy instrument'),
                    dt.fromisoformat('2021-08-05T15:00:00-06:00'),
                    dt.fromisoformat('2021-08-05T16:00:00-06:00'),
                    user='***REMOVED***')
        with pytest.raises(LookupError) as e:
            nemo.get_connector_for_session(s)

        assert "Did not find enabled NEMO harvester for " \
               "\"Dummy instrument\"" in str(e.value)

    def test_bad_res_question_value(self, nemo_connector):
        from nexusLIMS.harvesters import nemo
        dt_from = dt.fromisoformat('2021-08-02T00:00:00-06:00')
        dt_to = dt.fromisoformat('2021-08-03T00:00:00-06:00')
        res = nemo_connector.get_reservations(tool_id=3,
                                              dt_from=dt_from, dt_to=dt_to)[0]
        val = nemo._get_res_question_value('bad_value', res)
        assert val is None

    def test_no_res_questions(self, nemo_connector):
        from nexusLIMS.harvesters import nemo
        dt_from = dt.fromisoformat('2021-09-06T00:00:00-06:00')
        dt_to = dt.fromisoformat('2021-09-07T00:00:00-06:00')
        res = nemo_connector.get_reservations(tool_id=10,
                                              dt_from=dt_from, dt_to=dt_to)[0]
        val = nemo._get_res_question_value('project_id', res)
        assert val is None

    def test_bad_id_from_url(self):
        from nexusLIMS.harvesters import nemo
        this_id = nemo.id_from_url('https://test.com/?notid=4')
        assert this_id is None

class TestReservationEvent:
    def test_full_reservation_constructor(self):
        res_event = ReservationEvent(
            experiment_title="A test title",
            instrument=instrument_db['FEI-Titan-TEM-635816'],
            last_updated=dt.fromisoformat("2021-09-15T16:04:00"),
            username='***REMOVED***', created_by='***REMOVED***',
            start_time=dt.fromisoformat("2021-09-15T03:00:00"),
            end_time=dt.fromisoformat("2021-09-15T16:00:00"),
            reservation_type="A test event",
            experiment_purpose="To test the constructor",
            sample_details="A sample that was loaded into a microscope for "
                           "testing",
            sample_pid=["***REMOVED***.5"],
            sample_name="The test sample",
            project_name="NexusLIMS", project_id="***REMOVED***.1.5",
            project_ref="https://www.example.org", internal_id="42308",
            division="641", group="00"
        )

        xml = res_event.as_xml()
        assert xml.find('title').text == "A test title"
        assert xml.find('id').text == "42308"
        assert xml.find('summary/experimenter').text == "***REMOVED***"
        assert xml.find('summary/instrument').text == "FEI Titan TEM"
        assert xml.find('summary/instrument').get("pid") == \
               "FEI-Titan-TEM-635816"
        assert xml.find('summary/reservationStart').text == \
               "2021-09-15T03:00:00"
        assert xml.find('summary/reservationEnd').text == "2021-09-15T16:00:00"
        assert xml.find('summary/motivation').text == "To test the constructor"
        assert xml.find('sample').get("id") == "***REMOVED***.5"
        assert xml.find('sample/name').text == "The test sample"
        assert xml.find('sample/description').text == \
               "A sample that was loaded into a microscope for testing"
        assert xml.find('project/name').text == "NexusLIMS"
        assert xml.find('project/division').text == "641"
        assert xml.find('project/group').text == "00"
        assert xml.find('project/project_id').text == "***REMOVED***.1.5"
        assert xml.find('project/ref').text == "https://www.example.org"

    def test_res_event_without_title(self):
        res_event = ReservationEvent(
            experiment_title=None,
            instrument=instrument_db['FEI-Titan-TEM-635816'],
            last_updated=dt.fromisoformat("2021-09-15T16:04:00"),
            username='***REMOVED***', created_by='***REMOVED***',
            start_time=dt.fromisoformat("2021-09-15T04:00:00"),
            end_time=dt.fromisoformat("2021-09-15T17:00:00"),
            reservation_type="A test event",
            experiment_purpose="To test a reservation with no title",
            sample_details="A sample that was loaded into a microscope for "
                           "testing",
            sample_pid=["***REMOVED***.6"],
            sample_name="The test sample name",
            project_name="NexusLIMS", project_id="***REMOVED***.1.6",
            project_ref="https://www.example.org", internal_id="48328",
            division="641", group="00"
        )

        xml = res_event.as_xml()
        assert xml.find('title').text == "Experiment on the FEI Titan TEM on " \
                                         "Wednesday Sep. 15, 2021"
        assert xml.find('id').text == "48328"
        assert xml.find('summary/experimenter').text == "***REMOVED***"
        assert xml.find('summary/instrument').text == "FEI Titan TEM"
        assert xml.find('summary/instrument').get("pid") == \
               "FEI-Titan-TEM-635816"
        assert xml.find('summary/reservationStart').text == \
               "2021-09-15T04:00:00"
        assert xml.find('summary/reservationEnd').text == "2021-09-15T17:00:00"
        assert xml.find('summary/motivation').text == "To test a reservation " \
                                                      "with no title"
        assert xml.find('sample').get("id") == "***REMOVED***.6"
        assert xml.find('sample/name').text == "The test sample name"
        assert xml.find('sample/description').text == \
               "A sample that was loaded into a microscope for testing"
        assert xml.find('project/name').text == "NexusLIMS"
        assert xml.find('project/division').text == "641"
        assert xml.find('project/group').text == "00"
        assert xml.find('project/project_id').text == "***REMOVED***.1.6"
        assert xml.find('project/ref').text == "https://www.example.org"