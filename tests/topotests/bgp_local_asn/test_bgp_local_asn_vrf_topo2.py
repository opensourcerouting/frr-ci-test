#!/usr/bin/env python3
# SPDX-License-Identifier: ISC
#
# Copyright (c) 2022 by VMware, Inc. ("VMware")
# Used Copyright (c) 2018 by Network Device Education Foundation,
# Inc. ("NetDEF") in this file.
#

"""
1. Verify the BGP Local AS functionality by adding new AS when leaking routes
 from non-default VRF to non-default with route map by prefix lists.
"""

import os
import sys
import time
import pytest

# Save the Current Working Directory to find configuration files.
CWD = os.path.dirname(os.path.realpath(__file__))
sys.path.append(os.path.join(CWD, "../"))
sys.path.append(os.path.join(CWD, "../lib/"))

# pylint: disable=C0413
# Import topogen and topotest helpers
from lib.topogen import Topogen, get_topogen

from lib.common_config import (
    start_topology,
    write_test_header,
    create_static_routes,
    write_test_footer,
    reset_config_on_routers,
    verify_rib,
    step,
    check_address_types,
    check_router_status,
    create_static_routes,
    create_prefix_lists,
    verify_fib_routes,
    create_route_maps,
)

from lib.topolog import logger
from lib.bgp import (
    verify_bgp_convergence,
    verify_bgp_rib,
    create_router_bgp,
)
from lib.topojson import build_config_from_json

pytestmark = [pytest.mark.bgpd, pytest.mark.staticd]

# Global variables
BGP_CONVERGENCE = False
ADDR_TYPES = check_address_types()
NETWORK = {"ipv4": "10.1.1.0/32", "ipv6": "10:1::1:0/128"}
NEXT_HOP_IP = {"ipv4": "Null0", "ipv6": "Null0"}


def setup_module(mod):
    """
    Sets up the pytest environment

    * `mod`: module name
    """

    testsuite_run_time = time.asctime(time.localtime(time.time()))
    logger.info("Testsuite start time: {}".format(testsuite_run_time))
    logger.info("=" * 40)

    logger.info("Running setup_module to create topology")

    # This function initiates the topology build with Topogen...
    json_file = "{}/bgp_local_asn_vrf_topo2.json".format(CWD)
    tgen = Topogen(json_file, mod.__name__)
    global topo
    topo = tgen.json_topo
    # ... and here it calls Mininet initialization functions.

    # Starting topology, create tmp files which are loaded to routers
    #  to start daemons and then start routers
    start_topology(tgen)

    # Creating configuration from JSON
    build_config_from_json(tgen, topo)

    global BGP_CONVERGENCE
    global ADDR_TYPES
    ADDR_TYPES = check_address_types()

    BGP_CONVERGENCE = verify_bgp_convergence(tgen, topo)
    assert BGP_CONVERGENCE is True, "setup_module : Failed \n Error: {}".format(
        BGP_CONVERGENCE
    )

    logger.info("Running setup_module() done")


def teardown_module():
    """Teardown the pytest environment"""

    logger.info("Running teardown_module to delete topology")

    tgen = get_topogen()

    # Stop toplogy and Remove tmp files
    tgen.stop_topology()

    logger.info(
        "Testsuite end time: {}".format(time.asctime(time.localtime(time.time())))
    )
    logger.info("=" * 40)


################################################################################################
#
#   Testcases
#
###############################################################################################


def test_verify_local_asn_ipv4_import_from_non_default_to_non_default_VRF_p0(request):
    """
    Verify the BGP Local AS functionality by adding new AS when leaking routes
    from non-default VRF to non-default with route map by prefix lists.
    """
    tgen = get_topogen()
    global BGP_CONVERGENCE
    if BGP_CONVERGENCE != True:
        pytest.skip("skipped because of BGP Convergence failure")

    # test case name
    tc_name = request.node.name
    write_test_header(tc_name)
    if tgen.routers_have_failure():
        check_router_status(tgen)
    reset_config_on_routers(tgen)

    step("Base config is done as part of JSON")

    # configure static routes
    step("Advertise prefix 10.1.1.0/32 from Router-1(AS-100).")
    step("Advertise an ipv6 prefix 10:1::1:0/128 from Router-1(AS-100).")
    dut = "r2"
    for addr_type in ADDR_TYPES:
        # Enable static routes
        input_dict_static_route = {
            "r2": {
                "static_routes": [
                    {
                        "network": NETWORK[addr_type],
                        "next_hop": NEXT_HOP_IP[addr_type],
                        "vrf": "RED",
                    }
                ]
            }
        }

        logger.info("Configure static routes")
        result = create_static_routes(tgen, input_dict_static_route)
        assert result is True, "Testcase {} : Failed \n Error: {}".format(
            tc_name, result
        )

    step("configure redistribute static in Router BGP in R2")
    input_dict_static_route_redist = {
        "r2": {
            "bgp": {
                "local_as": 200,
                "vrf": "RED",
                "address_family": {
                    "ipv4": {
                        "unicast": {
                            "redistribute": [
                                {"redist_type": "static"},
                                {"redist_type": "connected"},
                            ]
                        }
                    },
                    "ipv6": {
                        "unicast": {
                            "redistribute": [
                                {"redist_type": "static"},
                                {"redist_type": "connected"},
                            ]
                        }
                    },
                },
            }
        }
    }
    result = create_router_bgp(tgen, topo, input_dict_static_route_redist)
    assert result is True, "Testcase {} : Failed \n Error: {}".format(tc_name, result)

    step("Configure import vrf BLUE from vrf RED on R3 under IPv4 Address Family")
    input_import_vrf_ipv4 = {
        "r3": {
            "bgp": [
                {
                    "local_as": 300,
                    "vrf": "BLUE",
                    "address_family": {
                        "ipv4": {"unicast": {"import": {"vrf": "RED"}}},
                        "ipv6": {"unicast": {"import": {"vrf": "RED"}}},
                    },
                }
            ]
        }
    }
    result = create_router_bgp(tgen, topo, input_import_vrf_ipv4)
    assert result is True, "Testcase {} : Failed \n Error: {}".format(tc_name, result)

    step("Verify IPv4 and IPv6 static routes received on R3 VRF BLUE & R4 VRF BLUE")
    for addr_type in ADDR_TYPES:
        static_routes_input = {
            "r2": {
                "static_routes": [
                    {
                        "network": NETWORK[addr_type],
                        "next_hop": NEXT_HOP_IP[addr_type],
                        "vrf": "BLUE",
                    }
                ]
            }
        }
        for dut in ["r3", "r4"]:
            result = verify_fib_routes(tgen, addr_type, dut, static_routes_input)
            assert result is True, "Testcase {} : Failed \n Error: {}".format(
                tc_name, result
            )
            result = verify_bgp_rib(tgen, addr_type, dut, static_routes_input)
            assert result is True, "Testcase {} : Failed \n Error: {}".format(
                tc_name, result
            )

    step("Configure local-as at R3 towards R2.")
    for addr_type in ADDR_TYPES:
        input_dict_r3_to_r2 = {
            "r3": {
                "vrfs": [{"name": "RED", "id": "1"}],
                "bgp": [
                    {
                        "local_as": "300",
                        "vrf": "RED",
                        "address_family": {
                            addr_type: {
                                "unicast": {
                                    "neighbor": {
                                        "r2": {
                                            "dest_link": {
                                                "r3": {"local_asn": {"local_as": "110"}}
                                            }
                                        }
                                    }
                                }
                            }
                        },
                    }
                ],
            }
        }
        result = create_router_bgp(tgen, topo, input_dict_r3_to_r2)
        assert result is True, "Testcase {} :Failed \n Error: {}".format(
            tc_name, result
        )

    step("Configure local-as at R3 towards R4.")
    for addr_type in ADDR_TYPES:
        input_dict_r3_to_r4 = {
            "r3": {
                "vrfs": [{"name": "BLUE", "id": "1"}],
                "bgp": [
                    {
                        "local_as": "300",
                        "vrf": "BLUE",
                        "address_family": {
                            addr_type: {
                                "unicast": {
                                    "neighbor": {
                                        "r4": {
                                            "dest_link": {
                                                "r3": {"local_asn": {"local_as": "110"}}
                                            }
                                        }
                                    }
                                }
                            }
                        },
                    }
                ],
            }
        }
        result = create_router_bgp(tgen, topo, input_dict_r3_to_r4)
        assert result is True, "Testcase {} :Failed \n Error: {}".format(
            tc_name, result
        )

    step("Configure remote-as at R2 towards R3.")
    for addr_type in ADDR_TYPES:
        input_dict_r2_to_r3 = {
            "r2": {
                "vrfs": [{"name": "RED", "id": "1"}],
                "bgp": [
                    {
                        "local_as": "200",
                        "vrf": "RED",
                        "address_family": {
                            addr_type: {
                                "unicast": {
                                    "neighbor": {
                                        "r3": {
                                            "dest_link": {
                                                "r2": {
                                                    "local_asn": {"remote_as": "110"}
                                                }
                                            }
                                        }
                                    }
                                }
                            }
                        },
                    }
                ],
            }
        }
        result = create_router_bgp(tgen, topo, input_dict_r2_to_r3)
        assert result is True, "Testcase {} :Failed \n Error: {}".format(
            tc_name, result
        )

    step("Configure remote-as at R4 towards R3.")
    for addr_type in ADDR_TYPES:
        input_dict_r4_to_r3 = {
            "r4": {
                "vrfs": [{"name": "BLUE", "id": "1"}],
                "bgp": [
                    {
                        "local_as": "400",
                        "vrf": "BLUE",
                        "address_family": {
                            addr_type: {
                                "unicast": {
                                    "neighbor": {
                                        "r3": {
                                            "dest_link": {
                                                "r4": {
                                                    "local_asn": {"remote_as": "110"}
                                                }
                                            }
                                        }
                                    }
                                }
                            }
                        },
                    }
                ],
            }
        }
        result = create_router_bgp(tgen, topo, input_dict_r4_to_r3)
        assert result is True, "Testcase {} :Failed \n Error: {}".format(
            tc_name, result
        )

    step("BGP neighborship is verified by following commands in R3 routers")
    BGP_CONVERGENCE = verify_bgp_convergence(tgen, topo)
    assert BGP_CONVERGENCE is True, "BGP convergence :Failed \n Error: {}".format(
        BGP_CONVERGENCE
    )

    step("Verify IPv4 and IPv6 static routes received on R3 VRF BLUE & R4 VRF BLUE")
    for addr_type in ADDR_TYPES:
        static_routes_input = {
            "r2": {
                "static_routes": [
                    {
                        "network": NETWORK[addr_type],
                        "next_hop": NEXT_HOP_IP[addr_type],
                        "vrf": "BLUE",
                    }
                ]
            }
        }
        for dut in ["r3", "r4"]:
            result = verify_fib_routes(tgen, addr_type, dut, static_routes_input)
            assert result is True, "Testcase {} : Failed \n Error: {}".format(
                tc_name, result
            )

            result = verify_bgp_rib(tgen, addr_type, dut, static_routes_input)
            assert result is True, "Testcase {} : Failed \n Error: {}".format(
                tc_name, result
            )

    step(
        "Verify that AS-110 is got added in the AS list 110 200 100 by following "
        " commands at R3 router."
    )
    dut = "r3"
    aspath = "110 200"
    for addr_type in ADDR_TYPES:
        input_static_r2 = {
            "r2": {"static_routes": [{"network": NETWORK[addr_type], "vrf": "BLUE"}]}
        }
        result = verify_bgp_rib(tgen, addr_type, dut, input_static_r2, aspath=aspath)
        assert result is True, "Testcase {} : Failed \n Error: {}".format(
            tc_name, result
        )

    # configure the prefix-list and route-maps.
    for adt in ADDR_TYPES:
        # Create Static routes
        input_dict_rm1 = {
            "r2": {
                "static_routes": [
                    {
                        "network": NETWORK[adt],
                        "no_of_ip": 1,
                        "next_hop": NEXT_HOP_IP[adt],
                        "vrf": "RED",
                    }
                ]
            }
        }

        result = create_static_routes(tgen, input_dict_rm1)
        assert result is True, "Testcase {} : Failed \n Error: {}".format(
            tc_name, result
        )

        # Api call to redistribute static routes
        input_dict_rm_rd = {
            "r2": {
                "bgp": {
                    "local_as": 200,
                    "address_family": {
                        "ipv4": {
                            "unicast": {
                                "redistribute": [
                                    {"redist_type": "static"},
                                    {"redist_type": "connected"},
                                ]
                            }
                        },
                        "ipv6": {
                            "unicast": {
                                "redistribute": [
                                    {"redist_type": "static"},
                                    {"redist_type": "connected"},
                                ]
                            }
                        },
                    },
                }
            }
        }

        result = create_router_bgp(tgen, topo, input_dict_rm_rd)
        assert result is True, "Testcase {} : Failed \n Error: {}".format(
            tc_name, result
        )

        input_dict_rm_pl = {
            "r3": {
                "prefix_lists": {
                    "ipv4": {
                        "pf_list_1_ipv4": [
                            {
                                "seqid": 10,
                                "action": "permit",
                                "network": NETWORK["ipv4"],
                            }
                        ]
                    },
                    "ipv6": {
                        "pf_list_1_ipv6": [
                            {
                                "seqid": 100,
                                "action": "permit",
                                "network": NETWORK["ipv6"],
                            }
                        ]
                    },
                }
            }
        }
        result = create_prefix_lists(tgen, input_dict_rm_pl)
        assert result is True, "Testcase {} : Failed \n Error: {}".format(
            tc_name, result
        )

        # Create route map
        for addr_type in ADDR_TYPES:
            input_dict_rm_r3 = {
                "r3": {
                    "route_maps": {
                        "rmap_match_tag_1_{}".format(addr_type): [
                            {
                                "action": "permit",
                                "match": {
                                    addr_type: {
                                        "prefix_lists": "pf_list_1_{}".format(addr_type)
                                    }
                                },
                            }
                        ],
                        "rmap_match_tag_2_{}".format(addr_type): [
                            {
                                "action": "permit",
                                "match": {
                                    addr_type: {
                                        "prefix_lists": "pf_list_2_{}".format(addr_type)
                                    }
                                },
                            }
                        ],
                    }
                }
            }
            result = create_route_maps(tgen, input_dict_rm_r3)
            assert result is True, "Testcase {} : Failed \n Error: {}".format(
                tc_name, result
            )

        # Configure neighbor for route map
        input_dict_conf_neighbor_rm = {
            "r3": {
                "bgp": [
                    {
                        "local_as": "300",
                        "vrf": "BLUE",
                        "address_family": {
                            "ipv4": {
                                "unicast": {
                                    "neighbor": {
                                        "r4": {
                                            "dest_link": {
                                                "r3": {
                                                    "route_maps": [
                                                        {
                                                            "name": "rmap_match_tag_1_ipv4",
                                                            "direction": "out",
                                                        },
                                                        {
                                                            "name": "rmap_match_tag_1_ipv4",
                                                            "direction": "out",
                                                        },
                                                    ]
                                                }
                                            }
                                        }
                                    }
                                }
                            },
                            "ipv6": {
                                "unicast": {
                                    "neighbor": {
                                        "r4": {
                                            "dest_link": {
                                                "r3": {
                                                    "route_maps": [
                                                        {
                                                            "name": "rmap_match_tag_1_ipv6",
                                                            "direction": "in",
                                                        },
                                                        {
                                                            "name": "rmap_match_tag_1_ipv6",
                                                            "direction": "out",
                                                        },
                                                    ]
                                                }
                                            }
                                        }
                                    }
                                }
                            },
                        },
                    }
                ]
            }
        }

        result = create_router_bgp(tgen, topo, input_dict_conf_neighbor_rm)
        assert result is True, "Testcase {} : Failed \n Error: {}".format(
            tc_name, result
        )

    for adt in ADDR_TYPES:
        # Verifying RIB routes
        dut = "r3"
        input_dict_r2_rib = {
            "r2": {
                "static_routes": [
                    {
                        "network": [NETWORK[adt]],
                        "no_of_ip": 1,
                        "next_hop": NEXT_HOP_IP[adt],
                        "vrf": "RED",
                    }
                ]
            }
        }
        result = verify_rib(tgen, adt, dut, input_dict_r2_rib)
        assert result is True, "Testcase {}: Failed \n Error: {}".format(
            tc_name, result
        )

        # Verifying RIB routes
        dut = "r4"
        input_dict_r2_rib = {
            "r2": {
                "static_routes": [
                    {
                        "network": [NETWORK[adt]],
                        "no_of_ip": 1,
                        "next_hop": NEXT_HOP_IP[adt],
                        "vrf": "BLUE",
                    }
                ]
            }
        }
        result = verify_rib(tgen, adt, dut, input_dict_r2_rib)
        assert result is True, "Testcase {}: Failed \n Error: {}".format(
            tc_name, result
        )

    step("Configure local-as with no-prepend at R3 towards R2.")
    for addr_type in ADDR_TYPES:
        input_dict_no_prep_r3_to_r2 = {
            "r3": {
                "vrfs": [{"name": "RED", "id": "1"}],
                "bgp": [
                    {
                        "local_as": "300",
                        "vrf": "RED",
                        "address_family": {
                            addr_type: {
                                "unicast": {
                                    "neighbor": {
                                        "r2": {
                                            "dest_link": {
                                                "r3": {
                                                    "local_asn": {
                                                        "local_as": "110",
                                                        "no_prepend": True,
                                                    }
                                                }
                                            }
                                        }
                                    }
                                }
                            }
                        },
                    }
                ],
            }
        }
        result = create_router_bgp(tgen, topo, input_dict_no_prep_r3_to_r2)
        assert result is True, "Testcase {} :Failed \n Error: {}".format(
            tc_name, result
        )

    step("Configure local-as with no-prepend at R3 towards R4.")
    for addr_type in ADDR_TYPES:
        input_dict_no_prep_r3_to_r4 = {
            "r3": {
                "vrfs": [{"name": "BLUE", "id": "1"}],
                "bgp": [
                    {
                        "local_as": "300",
                        "vrf": "BLUE",
                        "address_family": {
                            addr_type: {
                                "unicast": {
                                    "neighbor": {
                                        "r4": {
                                            "dest_link": {
                                                "r3": {
                                                    "local_asn": {
                                                        "local_as": "110",
                                                        "no_prepend": True,
                                                    }
                                                }
                                            }
                                        }
                                    }
                                }
                            }
                        },
                    }
                ],
            }
        }
        result = create_router_bgp(tgen, topo, input_dict_no_prep_r3_to_r4)
        assert result is True, "Testcase {} :Failed \n Error: {}".format(
            tc_name, result
        )

    step("BGP neighborship is verified by following commands in R3 routers")
    BGP_CONVERGENCE = verify_bgp_convergence(tgen, topo)
    assert BGP_CONVERGENCE is True, "BGP convergence :Failed \n Error: {}".format(
        BGP_CONVERGENCE
    )

    dut = "r3"
    aspath = "200"
    for addr_type in ADDR_TYPES:
        input_static_r2 = {
            "r2": {"static_routes": [{"network": NETWORK[addr_type], "vrf": "BLUE"}]}
        }
        result = verify_bgp_rib(tgen, addr_type, dut, input_static_r2, aspath=aspath)
        assert result is True, "Testcase {} : Failed \n Error: {}".format(
            tc_name, result
        )

    step("Configure local-as with no-prepend and replace-as at R3 towards R2")
    for addr_type in ADDR_TYPES:
        input_dict_no_prep_rep_as_r3_to_r2 = {
            "r3": {
                "vrfs": [{"name": "RED", "id": "1"}],
                "bgp": [
                    {
                        "local_as": "300",
                        "vrf": "RED",
                        "address_family": {
                            addr_type: {
                                "unicast": {
                                    "neighbor": {
                                        "r2": {
                                            "dest_link": {
                                                "r3": {
                                                    "local_asn": {
                                                        "local_as": "110",
                                                        "no_prepend": True,
                                                        "replace_as": True,
                                                    }
                                                }
                                            }
                                        }
                                    }
                                }
                            }
                        },
                    }
                ],
            }
        }
        result = create_router_bgp(tgen, topo, input_dict_no_prep_rep_as_r3_to_r2)
        assert result is True, "Testcase {} :Failed \n Error: {}".format(
            tc_name, result
        )

    step("Configure local-as with no-prepend and replace-as at R3 towards R4")
    for addr_type in ADDR_TYPES:
        input_dict_no_prep_rep_as_r3_to_r4 = {
            "r3": {
                "vrfs": [{"name": "BLUE", "id": "1"}],
                "bgp": [
                    {
                        "local_as": "300",
                        "vrf": "BLUE",
                        "address_family": {
                            addr_type: {
                                "unicast": {
                                    "neighbor": {
                                        "r4": {
                                            "dest_link": {
                                                "r3": {
                                                    "local_asn": {
                                                        "local_as": "110",
                                                        "no_prepend": True,
                                                        "replace_as": True,
                                                    }
                                                }
                                            }
                                        }
                                    }
                                }
                            }
                        },
                    }
                ],
            }
        }
        result = create_router_bgp(tgen, topo, input_dict_no_prep_rep_as_r3_to_r4)
        assert result is True, "Testcase {} :Failed \n Error: {}".format(
            tc_name, result
        )

    step("BGP neighborship is verified by following commands in R3 routers")
    BGP_CONVERGENCE = verify_bgp_convergence(tgen, topo)
    assert BGP_CONVERGENCE is True, "BGP convergence :Failed \n Error: {}".format(
        BGP_CONVERGENCE
    )

    dut = "r4"
    aspath = "110 200"
    for addr_type in ADDR_TYPES:
        input_static_r2 = {
            "r2": {"static_routes": [{"network": NETWORK[addr_type], "vrf": "BLUE"}]}
        }
        result = verify_bgp_rib(tgen, addr_type, dut, input_static_r2, aspath=aspath)
        assert result is True, "Testcase {} : Failed \n Error: {}".format(
            tc_name, result
        )

    write_test_footer(tc_name)


if __name__ == "__main__":
    args = ["-s"] + sys.argv[1:]
    sys.exit(pytest.main(args))
