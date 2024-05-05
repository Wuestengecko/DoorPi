import pjsua2 as pj


def main() -> None:
    """List all devices that PJSIP detected."""
    ep = pj.Endpoint()
    ep.libCreate()
    ep.libInit(pj.EpConfig())
    adm = ep.audDevManager()
    devices = [f"  {dev.driver}:{dev.name}" for dev in adm.enumDev2()]
    ep.libDestroy()

    print("\nFound audio devices:")
    if not devices:
        print("  (No audio devices found)")
    else:
        for dev in devices:
            print(dev)


if __name__ == "__main__":
    main()
