from unittest import mock

from doorpi.sipphone import from_dummy

from ..mocks import DoorPi, DoorPiTestCase


@mock.patch("doorpi.INSTANCE", new_callable=DoorPi)
class DummyPhoneTest(DoorPiTestCase):
    def test_creating_DummyPhone_registers_lifecycle_events_and_fires_oncreate(
        self, instance
    ):
        from_dummy.instantiate()
        instance.event_handler.register_event.assert_has_calls(
            [
                mock.call("OnSIPPhoneCreate", "doorpi.sipphone.from_dummy"),
                mock.call("OnSIPPhoneStart", "doorpi.sipphone.from_dummy"),
                mock.call("OnSIPPhoneDestroy", "doorpi.sipphone.from_dummy"),
            ],
            any_order=True,
        )
        instance.event_handler.assert_called_once_with(
            "OnSIPPhoneCreate", "doorpi.sipphone.from_dummy"
        )

    def test_start_fires_onstart(self, instance):
        from_dummy.instantiate().start()
        instance.event_handler.assert_has_calls(
            [
                mock.call("OnSIPPhoneCreate", "doorpi.sipphone.from_dummy"),
                mock.call("OnSIPPhoneStart", "doorpi.sipphone.from_dummy"),
            ],
            any_order=True,
        )

    def test_stop_fires_ondestroy(self, instance):
        from_dummy.instantiate().stop()
        instance.event_handler.assert_has_calls(
            [
                mock.call("OnSIPPhoneCreate", "doorpi.sipphone.from_dummy"),
                mock.call("OnSIPPhoneDestroy", "doorpi.sipphone.from_dummy"),
            ],
            any_order=True,
        )

    def test_call_logs(self, _):
        uri = "sip:test@test"
        phone = from_dummy.instantiate()
        with self.assertLogs("doorpi.sipphone.from_dummy", "INFO"):
            phone.call(uri)

    def test_hangup_logs(self, _):
        phone = from_dummy.instantiate()
        with self.assertLogs("doorpi.sipphone.from_dummy", "INFO"):
            phone.hangup()

    def test_nothing_is_admin(self, _):
        uri = "sip:test@test"
        phone = from_dummy.instantiate()
        self.assertFalse(phone.is_admin(uri))

    def test_call_dump_is_empty(self, _):
        phone = from_dummy.instantiate()
        self.assertEqual(phone.dump_call(), {})
