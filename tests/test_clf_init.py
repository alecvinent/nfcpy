# -*- coding: latin-1 -*-
from __future__ import absolute_import, division

import nfc
import nfc.clf

import errno
import pytest
from pytest_mock import mocker  # noqa: F401

import logging
logging.basicConfig(level=logging.DEBUG)
logging_level = logging.getLogger().getEffectiveLevel()
logging.getLogger("nfc.clf").setLevel(logging_level)


def HEX(s):
    return bytearray.fromhex(s) if s is not None else None


def test_print_data():
    assert nfc.clf.print_data(None) == 'None'
    assert nfc.clf.print_data(b'1') == '31'
    assert nfc.clf.print_data(bytearray.fromhex('01')) == '01'


class TestContactlessFrontend(object):
    @pytest.fixture()  # noqa: F811
    def device_connect(self, mocker):
        return mocker.patch('nfc.clf.device.connect')

    @pytest.fixture()  # noqa: F811
    def device(self, mocker):
        return mocker.Mock(spec=nfc.clf.device.Device)

    @pytest.fixture()  # noqa: F811
    def clf(self, device_connect, device):
        device_connect.return_value = device
        clf = nfc.clf.ContactlessFrontend('test')
        device_connect.assert_called_once_with('test')
        assert isinstance(clf, nfc.clf.ContactlessFrontend)
        assert isinstance(clf.device, nfc.clf.device.Device)
        clf.device.sense_tta.return_value = None
        clf.device.sense_ttb.return_value = None
        clf.device.sense_ttf.return_value = None
        clf.device.sense_dep.return_value = None
        clf.device.listen_tta.return_value = None
        clf.device.listen_ttb.return_value = None
        clf.device.listen_ttf.return_value = None
        clf.device.listen_dep.return_value = None
        return clf

    @pytest.fixture()  # noqa: F811
    def terminate(self, mocker):
        return mocker.Mock(return_value=False)

    def test_init(self, device_connect):
        device_connect.return_value = None
        with pytest.raises(IOError) as excinfo:
            nfc.clf.ContactlessFrontend('test')
        assert excinfo.value.errno == errno.ENODEV

    def test_open(self, device_connect, device):
        device_connect.return_value = None
        assert nfc.clf.ContactlessFrontend().open('test') is False

        device_connect.return_value = device
        assert nfc.clf.ContactlessFrontend().open('test') is True

        with pytest.raises(TypeError) as excinfo:
            nfc.clf.ContactlessFrontend().open(int())
        assert str(excinfo.value) == "expecting a string type argument *path*"

        with pytest.raises(ValueError) as excinfo:
            nfc.clf.ContactlessFrontend().open('')
        assert str(excinfo.value) == "argument *path* must not be empty"

    def test_close(self, clf):
        clf.device.close.side_effect = IOError
        clf.close()

    #
    # CONNECT
    #

    def test_connect_without_device(self, clf):
        clf.device = None
        with pytest.raises(IOError) as excinfo:
            clf.connect()
        assert excinfo.value.errno == errno.ENODEV

    @pytest.mark.parametrize("options, errstr", [
        ({'rdwr': str()}, "'rdwr' must be a dictionary"),
        ({'llcp': int()}, "'llcp' must be a dictionary"),
        ({'card': set()}, "'card' must be a dictionary"),
    ])
    def test_connect_with_invalid_options(self, clf, options, errstr):
        with pytest.raises(TypeError) as excinfo:
            clf.connect(**options)
        assert str(excinfo.value) == "argument " + errstr

    def test_connect_with_empty_options(self, clf):
        assert clf.connect() is None

    def test_connect_with_startup_false(self, clf):
        assert clf.connect(llcp={'on-startup': lambda llc: False}) is None
        assert clf.connect(rdwr={'on-startup': lambda llc: False}) is None
        assert clf.connect(card={'on-startup': lambda llc: False}) is None

    def test_connect_with_terminate_true(self, clf, terminate):
        terminate.return_value = True
        assert clf.connect(llcp={}, terminate=terminate) is None
        assert clf.connect(rdwr={}, terminate=terminate) is None
        assert clf.connect(card={}, terminate=terminate) is None

    def test_connect_llcp_initiator(self, clf, terminate):
        terminate.side_effect = [False, True]
        assert clf.connect(llcp={}, terminate=terminate) is None

    def test_connect_rdwr_defaults(self, clf, terminate):
        terminate.side_effect = [False, True]
        rdwr_options = {'iterations': 1}
        assert clf.connect(rdwr=rdwr_options, terminate=terminate) is None

    def test_connect_card_defaults(self, clf, terminate):
        terminate.side_effect = [False, True]
        card_options = {'on-startup': lambda _: nfc.clf.LocalTarget('212F')}
        assert clf.connect(card=card_options, terminate=terminate) is None

    @pytest.mark.parametrize("error", [
        IOError, nfc.clf.UnsupportedTargetError, KeyboardInterrupt,
    ])
    def test_connect_false_on_error(self, clf, error):
        clf.device.sense_tta.side_effect = error
        clf.device.sense_ttb.side_effect = error
        clf.device.sense_ttf.side_effect = error
        clf.device.sense_dep.side_effect = error
        llcp_options = {'role': 'initiator'}
        assert clf.connect(llcp=llcp_options) is False

    def test_connect_rdwr_found_tta_target(self, clf, terminate):
        terminate.side_effect = [False, True]
        target = nfc.clf.RemoteTarget('106A')
        target.rid_res = HEX('1148 B2565400')
        target.sens_res = HEX('000C')
        clf.device.sense_tta.return_value = target
        rdwr_options = {'iterations': 1, 'targets': ['106A']}
        assert clf.connect(rdwr=rdwr_options, terminate=terminate) is True

    #
    # SENSE
    #

    def test_sense_without_targets(self, clf):
        assert clf.sense() is None

    def test_sense_without_device(self, clf):
        clf.device = None
        with pytest.raises(IOError) as excinfo:
            clf.sense(nfc.clf.RemoteTarget('106A'))
        assert excinfo.value.errno == errno.ENODEV

    def test_sense_with_invalid_targets(self, clf):
        with pytest.raises(ValueError) as excinfo:
            clf.sense(nfc.clf.RemoteTarget('106A'), nfc.clf.LocalTarget())
        assert str(excinfo.value).startswith("invalid target argument type")

    def test_sense_with_unknown_technology(self, clf):
        valid_target = nfc.clf.RemoteTarget('106A')
        wrong_target = nfc.clf.RemoteTarget('106X')
        with pytest.raises(nfc.clf.UnsupportedTargetError) as excinfo:
            clf.sense(wrong_target)
        assert str(excinfo.value) == "unknown technology type in '106X'"
        assert clf.sense(wrong_target, valid_target) is None
        clf.device.sense_tta.assert_called_once_with(valid_target)

    def test_sense_with_communication_error(self, clf):
        clf.device.sense_tta.side_effect = nfc.clf.CommunicationError
        target = nfc.clf.RemoteTarget('106A')
        assert clf.sense(target) is None
        clf.device.sense_tta.assert_called_once_with(target)

    @pytest.mark.parametrize("sens, sel, sdd, rid", [
        ('000C', None, None, '1148B2565400'),
        ('4400', '00', '0416C6C2D73881', None),
        ('E00C', '00', '0416C6C2D73881', '1148B2565400'),
    ])
    def test_sense_tta_found_valid_target(self, clf, sens, sel, sdd, rid):
        req_target = nfc.clf.RemoteTarget('106A')
        res_target = nfc.clf.RemoteTarget('106A')
        res_target.sens_res = HEX(sens)
        res_target.sel_res = HEX(sel)
        res_target.sdd_res = HEX(sdd)
        res_target.rid_res = HEX(rid)
        clf.device.sense_tta.return_value = res_target
        res_target = clf.sense(req_target)
        assert isinstance(res_target, nfc.clf.RemoteTarget)
        clf.device.sense_tta.assert_called_once_with(req_target)

    @pytest.mark.parametrize("sens, sel, sdd, rid", [
        ('E00C', '00', '0416C6C2D73881', '000000000000'),
        ('E00C', '00', '0416C6C2D73881', '0000000000'),
        ('E00C', '00', '0416C6C2D73881', None),
        ('E000', '00', '0416C6C2D73881', '100000000000'),
        ('E00000', '00', '0416C6C2D73881', None),
        ('E0', '00', '0416C6C2D73881', None),
    ])
    def test_sense_tta_found_error_target(self, clf, sens, sel, sdd, rid):
        req_target = nfc.clf.RemoteTarget('106A')
        res_target = nfc.clf.RemoteTarget('106A')
        res_target.sens_res = HEX(sens)
        res_target.sel_res = HEX(sel)
        res_target.sdd_res = HEX(sdd)
        res_target.rid_res = HEX(rid)
        clf.device.sense_tta.return_value = res_target
        assert clf.sense(req_target) is None
        clf.device.sense_tta.assert_called_once_with(req_target)

    def test_sense_tta_invalid_sel_req(self, clf):
        target = nfc.clf.RemoteTarget('106A')
        target.sel_req = HEX('0011')
        with pytest.raises(ValueError) as excinfo:
            clf.sense(target)
        assert str(excinfo.value) == "sel_req must be 4, 7, or 10 byte"

    def test_sense_dep_invalid_atr_req(self, clf):
        target = nfc.clf.RemoteTarget('106A')
        target.atr_req = bytearray(15)
        with pytest.raises(ValueError) as excinfo:
            clf.sense(target)
        assert str(excinfo.value) == "minimum atr_req length is 16 byte"
        target.atr_req = bytearray(65)
        with pytest.raises(ValueError) as excinfo:
            clf.sense(target)
        assert str(excinfo.value) == "maximum atr_req length is 64 byte"

    def test_sense_ttb_found_tt4_target(self, clf):
        req_target = nfc.clf.RemoteTarget('106B')
        res_target = nfc.clf.RemoteTarget('106B')
        res_target.sensb_res = HEX('50E8253EEC00000011008185')
        clf.device.sense_ttb.return_value = res_target
        res_target = clf.sense(req_target)
        assert isinstance(res_target, nfc.clf.RemoteTarget)
        clf.device.sense_ttb.assert_called_once_with(req_target)


class TestRemoteTarget(object):
    @pytest.mark.parametrize("brty, send, recv, kwargs", [
        ('106A', '106A', '106A', {}),
        ('106A/212F', '106A', '212F', {}),
        ('106A', '106A', '106A', {'sens_req': HEX('0102'), 'integer': 5}),
    ])
    def test_init(self, brty, send, recv, kwargs):
        target = nfc.clf.RemoteTarget(brty, **kwargs)
        assert str(target).startswith(send)
        assert target.brty == send
        assert target.brty_send == send
        assert target.brty_recv == recv
        assert target.some_attribute is None
        for attr in kwargs:
            assert getattr(target, attr) == kwargs[attr]

    @pytest.mark.parametrize("brty", [
        '106', 'A106', '106/106',
    ])
    def test_init_fail(self, brty):
        with pytest.raises(ValueError) as excinfo:
            nfc.clf.RemoteTarget(brty)
        assert str(excinfo.value) == \
            "brty pattern does not match for '%s'" % brty

    @pytest.mark.parametrize("target1, target2", [
        (nfc.clf.RemoteTarget('106A'), nfc.clf.RemoteTarget('106A')),
        (nfc.clf.RemoteTarget('106A/106A'), nfc.clf.RemoteTarget('106A')),
        (nfc.clf.RemoteTarget('106A', a=1), nfc.clf.RemoteTarget('106A', a=1)),
    ])
    def test_is_equal(self, target1, target2):
        assert target1 == target2

    @pytest.mark.parametrize("target1, target2", [
        (nfc.clf.RemoteTarget('106A'), nfc.clf.RemoteTarget('212F')),
        (nfc.clf.RemoteTarget('106A/212F'), nfc.clf.RemoteTarget('106A')),
        (nfc.clf.RemoteTarget('106A', a=1), nfc.clf.RemoteTarget('106A', b=1)),
    ])
    def test_not_equal(self, target1, target2):
        assert target1 != target2


class TestLocalTarget(object):
    @pytest.mark.parametrize("brty, kwargs", [
        ('106A', {}),
        ('212A', {'sens_req': HEX('0102'), 'integer': 5}),
    ])
    def test_init(self, brty, kwargs):
        target = nfc.clf.LocalTarget(brty, **kwargs)
        assert target.brty == brty
        assert str(target).startswith(brty)
        assert target.some_attribute is None
        for attr in kwargs:
            assert getattr(target, attr) == kwargs[attr]

    @pytest.mark.parametrize("target1, target2", [
        (nfc.clf.LocalTarget(), nfc.clf.LocalTarget('106A')),
        (nfc.clf.LocalTarget('212F'), nfc.clf.LocalTarget('212F')),
        (nfc.clf.LocalTarget('106A', a=1), nfc.clf.LocalTarget('106A', a=1)),
    ])
    def test_is_equal(self, target1, target2):
        assert target1 == target2

    @pytest.mark.parametrize("target1, target2", [
        (nfc.clf.LocalTarget(), nfc.clf.LocalTarget('212F')),
        (nfc.clf.LocalTarget('212F'), nfc.clf.LocalTarget('106A')),
        (nfc.clf.LocalTarget('106A', a=1), nfc.clf.LocalTarget('106A', b=1)),
    ])
    def test_not_equal(self, target1, target2):
        assert target1 != target2