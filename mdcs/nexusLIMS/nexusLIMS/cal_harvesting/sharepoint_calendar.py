#! /usr/bin/env python
import os
import re
import logging
import requests

from requests_ntlm import HttpNtlmAuth
from lxml import etree
from dateparser import parse as dp_parse
from datetime import datetime
from configparser import ConfigParser

XSLT_PATH = os.path.join(os.path.dirname(__file__), "cal_parser.xsl")
INDENT = '  '

# DONE: test cases and automated testing
#       [x] will require installing pytest
# DONE: add new instruments to calendar handler


__all__ = ['AuthenticationError', 'get_auth', 'fetch_xml',
           'parse_xml', 'get_events', 'wrap_events', 'dump_calendars']


class AuthenticationError(Exception):
    """Class for showing an exception having to do with authentication"""
    def __init__(self, message):
        self.message = message


def get_auth(filename="credentials.ini"):
    """
    Set up NTLM authentication for the Microscopy Nexus using an account
    as specified from a file that lives in the package root named
    .credentials (or some other value provided as a parameter).
    Alternatively, the stored credentials can be overridden by supplying two
    environment variables: ``nexusLIMS_user`` and ``nexusLIMS_pass``. These
    variables will be queried first, and if not found, the method will
    attempt to use the credential file.

    Parameters
    ----------
    filename : str
        Name relative to this file (or absolute path) of file from which to
        read the parameters

    Returns
    -------
    auth : ``requests_ntlm.HttpNtlmAuth``
        NTLM authentication handler for ``requests``

    Notes
    -----
        The credentials file is expected to have a section named
        ``[nexus_credentials]`` and two values: ``username`` and
        ``password``. See the ``credentials.ini.example`` file included in
        the repository as an example.
    """
    try:
        username = os.environ['nexusLIMS_user']
        passwd = os.environ['nexusLIMS_pass']
        logging.info("Authenticating using environment variables")
    except KeyError:
        # if absolute path was provided, use that, otherwise find filename in
        # this directory
        if os.path.isabs(filename):
            pass
        else:
            filename = os.path.join(os.path.dirname(__file__), filename)

        # Raise error if the configuration file is not found
        if not os.path.isfile(filename):
            raise AuthenticationError("No credentials were specified with "
                                      "environment variables, and credential "
                                      "file {} was not found".format(filename))

        config = ConfigParser()
        config.read(filename)

        username = config.get("nexus_credentials", "username")
        passwd = config.get("nexus_credentials", "password")

    domain = 'nist'
    path = domain + '\\' + username

    auth = HttpNtlmAuth(path, passwd)

    return auth


def fetch_xml(instrument=None):
    """
    Get the XML responses from the Nexus Sharepoint calendar for one,
    multiple, or all instruments.

    Parameters
    ----------
    instrument : None, str, or list
        As defined in :py:func:`~.get_events`
        One or more of ['msed_titan', 'quanta', 'jeol_sem', 'hitachi_sem',
        'jeol_tem', 'cm30', 'em400', 'hitachi_s5500', 'mmsd_titan',
        'fei_helios_db'], or None. If None, events from all instruments will be
        returned.

    Returns
    -------
    api_response : list
        A list of strings containing the XML calendar information for each
        instrument requested, stripped of the empty default namespace
    """
    # DONE: parse instrument input and loop through to generate total output
    #       [x] add logic for getting list of instruments to process
    #       [x] concatenate XML output from each transform into single XML
    #           document

    # Paths for Nexus Instruments that can be booked through sharepoint
    # calendar, mapped to more user-friendly names
    # Instrument names can be found at
    # https://***REMOVED***/***REMOVED***/_vti_bin/ListData.svc
    # and
    # https://***REMOVED***nexuslims/NexusMicroscopyLIMS/wikis/Sharepoint-Calendar-Information
    instr_input_dict = {
        'msed_titan': "FEITitanTEMEvents",
        'quanta': "FEIQuanta200Events",
        'jeol_sem': "JEOLJSM7100Events",
        'hitachi_sem': "HitachiS4700Events",
        'jeol_tem': "JEOLJEM3010Events",
        'cm30': "PhilipsCM30Events",
        'em400': "PhilipsEM400Events",
        'hitachi_s5500': "HitachiS5500Events",
        'mmsd_titan': "FEITitanSTEMEvents",
        'fei_helios_db': "FEIHeliosDBEvents"
    }

    all_events = list(instr_input_dict.values())

    # Parse instrument parameter input
    if instrument is None:
        inst_to_fetch = all_events
    elif isinstance(instrument, str):
        inst_to_fetch = [instr_input_dict[instrument]]
    elif hasattr(instrument, '__iter__'):
        # instrument is a list, tuple, or some other iterable type, so map
        # inputted values to the events URL suffixes:
        inst_to_fetch = list(map(instr_input_dict.get, instrument))
    else:
        logging.warning('Entered instrument "{}" could not be parsed; '
                        'reverting to None...'.format(instrument))
        inst_to_fetch = all_events

    url = 'https://***REMOVED***/***REMOVED***/_vti_bin/' \
          'ListData.svc/'

    api_response = [''] * len(inst_to_fetch)

    for i, instr_name in enumerate(inst_to_fetch):
        instr_url = url + instr_name + '?$expand=CreatedBy'
        logging.info("Fetching Nexus calendar events from {}".format(instr_url))
        r = requests.get(instr_url, auth=get_auth())
        logging.info("  {} -- {} -- response: {}".format(instr_name,
                                                         instr_url,
                                                         r.status_code))

        if r.status_code == 401:
            # Authentication did not succeed and we received an *Unauthorized*
            # response from the server
            raise AuthenticationError('Could not authenticate to the Nexus '
                                      'SharePoint Calendar. Please check the '
                                      'credentials and try again.')

        if r.status_code == 200:
            # XML elements have a default namespace prefix (Atom format),
            # but lxml does not like an empty prefix, so it is easiest to
            # just sanitize the input and remove the namespaces as in
            # https://stackoverflow.com/a/18160164/1435788:
            xml = re.sub(r'\sxmlns="[^"]+"', '', r.text, count=1)

            # API returns utf-8 encoding, so encode correctly
            xml = bytes(xml, encoding='utf-8')
            api_response[i] = xml
        else:
            raise requests.exceptions.\
                ConnectionError('Could not access Nexus SharePoint Calendar '
                                'API at "{}"'.format(instr_url))

    return api_response


def parse_xml(xml, date=None, user=None):
    """
    Parse and translate an XML string from the API into a nicer format

    Parameters
    ----------
    xml : str or bytes
        A string containing XML, such as that returned by :py:func:`~.fetch_xml`
    date : None or str
        Either None or a YYYY-MM-DD date string indicating the date from
        which events should be fetched (note: the start time of each entry
        is what will be compared). If None, no date filtering will be
        performed.
    user : None or str
        Either None or a valid NIST username (the short format: e.g. "ear1"
        instead of ernst.august.ruska@nist.gov).

    Returns
    -------
    simplified_dom : ``lxml.XSLT`` transformation result
    """
    parser = etree.XMLParser(remove_blank_text=True, encoding='utf-8')

    # load XML structure from  string
    root = etree.fromstring(xml, parser)

    # use LXML to load XSLT stylesheet into xsl_transform
    # (note, etree.XSLT needs to be called on a root _Element
    # not an _ElementTree)
    xsl_dom = etree.parse(XSLT_PATH, parser).getroot()
    xsl_transform = etree.XSLT(xsl_dom)

    # setup parameters for passing to XSLT parser
    date_param = "''" if date is None else "'{}'".format(date)
    # DONE: parsing of username
    user_param = "''" if user is None else "'{}'".format(user)

    # do XSLT transformation
    simplified_dom = xsl_transform(root,
                                   date=date_param,
                                   user=user_param)

    return simplified_dom


# DONE: split up fetching calendar from server and parsing XML response
def get_events(instrument=None, date=None, user=None):
    """
    Get calendar events for a particular instrument on the Microscopy Nexus,
    on some date, or by some user

    Parameters
    ----------
    instrument : None, str, or list
        One or more of ['msed_titan', 'quanta', 'jeol_sem', 'hitachi_sem',
        'jeol_tem', 'cm30', 'em400', 'hitachi_s5500', 'mmsd_titan',
        'fei_helios_db'], or ``None``. If ``None``, all instruments will be
        returned.

    date : None or str
        Either None or a YYYY-MM-DD date string indicating the date from
        which events should be fetched (note: the start time of each entry
        is what will be compared). If None, no date filtering will be
        performed. Date will be parsed by :py:func:`dateparser.parse`,
        but providing the date in the ISO standard format is preferred for
        consistent behavior.

    user : None or str
        Either None or a valid NIST username (the short format: e.g. ``"ear1"``
        instead of ernst.august.ruska@nist.gov). If None, no user filtering
        will be performed. No verification of username is performed,
        so it is up to the user to make sure this is correct.

    Returns
    -------
    output : str
        A well-formed XML document in a string, containing one or more <event>
        tags that contain information about each reservation, including title,
        instrument, user information, reservation purpose, sample details,
        description, and date/time information.
    """

    # DONE: parsing of date
    # Use dateparser to get python datetime input, and return as YYYY-MM-DD
    if date is not None:
        date_datetime = dp_parse(date, settings={'STRICT_PARSING': True})
        if date_datetime:
            date = datetime.strftime(date_datetime, '%Y-%m-%d')
        else:
            logging.warning("Entered date could not be parsed; reverting to "
                            "None...")
            date = None

    output = ''
    xml_strings = fetch_xml(instrument)
    for xml in xml_strings:
        # parse the xml into a string, and then indent
        output += INDENT + str(parse_xml(xml, date, user)).\
            replace('\n', '\n' + INDENT)

    output = wrap_events(output)

    return output


def wrap_events(events_string):
    """
    Helper function to turn events string from :py:func:`~.get_events` into a
    well-formed XML file with proper indentation

    Parameters
    ----------
    events_string : str

    Returns
    -------
    result : str
        The full XML file as a string
    """
    # Holder for final XML output with proper header
    result = """<?xml version="1.0"?>
<events>
{}<dateRetrieved>{}</dateRetrieved>
""".format(INDENT, datetime.now().isoformat())
    # add indent to first line and all newlines:
    events_string = INDENT + events_string
    events_string = events_string.replace('\n', '\n' + INDENT)
    result += events_string
    result = result.strip().strip('\n')
    result += "\n</events>"

    return result


def dump_calendars(instrument=None, user=None, date=None,
                   filename='cal_events.xml'):
    """
    Write the results of :py:func:`~.get_events` to a file
    """
    with open(filename, 'w') as f:
        text = get_events(instrument=instrument, date=date, user=user)
        f.write(text)


# if __name__ == '__main__':
#     """
#     These lines are just for testing. For real use, import the methods you
#     need and operate from there
#     """
    # logging.basicConfig(level=logging.INFO)
    # dump_calendars(instrument='msed_titan')
    # dump_calendars(date='2019-02-28')
    # logging.info(get_events(instrument=None))
    # logging.info(get_events(date='2019-02-25'))
    # logging.info(get_events(user='***REMOVED***'))
    # logging.info(get_events(date='2018-12-26', user='***REMOVED***'))
    # logging.info(get_events())
