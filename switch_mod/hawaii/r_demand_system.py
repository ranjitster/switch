"""
Bridge to R demand system. 

Note that calibration data is stored in the R instance, and rpy2 only 
creates one instance. So this module can only be used with one model 
at a time (or at least only with models that use the same calibration data).

An alternative approach would be to store calibration data in a particular
environment or object in R, and return that to Python. Then that could be
returned by the python calibrate() function and attached to the model.
"""
# print "loading r_demand_system.py"

import numpy as np
import rpy2.robjects as robjects

# turn on automatic numpy <-> r conversion
import rpy2.robjects.numpy2ri
rpy2.robjects.numpy2ri.activate()

# alternatively, we could use numpy2ri(np.array(...)), but it's easier
# to use the automatic conversions. 
# If we wanted to be more explicit about conversions, it would probably 
# be best to switch to using the rpy2.rinterface to build up the r objects
# from a low level, e.g., rinterface.StrSexpVector(load_zones) to get a 
# string vector, other tools to get an array and add dimnames, etc.

# initialize the R environment
r = robjects.r

def define_arguments(argparser):
    argparser.add_argument("--dr-r-script", default=None,
        help="Name of R script to use for preparing demand response bids. "
        "Only takes effect when using --dr-demand-module=r_demand_system. "
        "This script should provide calibrate() and bid() functions. "
        )

def define_components(m):
    # load the R script specified by the user (must have calibrate() and bid() functions)
    if m.options.dr_r_script is None:
        raise RuntimeError(
            "No R script specified for use with the r_demand_system; unable to continue. "
            "Please use --dr-r-script <scriptname.R> in options.txt, scenarios.txt or on "
            "the command line."
        )
    r.source(m.options.dr_r_script)

def calibrate(base_data, dr_elasticity_scenario=1):
    """Accept a list of tuples showing load_zone, time_series, [base hourly loads], [base hourly prices]
    for each load_zone and time_series (day). Perform any calibration needed in the demand system
    so that customized bids can later be generated for each load_zone and time_series, using new prices.
    Also accept an allocation among different elasticity classes (defined in the R module.)
    """
    base_load_dict = {
        (lz, ts): base_loads
        for (lz, ts, base_loads, base_prices) in base_data
    }
    base_price_dict = {
        (lz, ts): base_prices
        for (lz, ts, base_loads, base_prices) in base_data
    }
    load_zones = unique_list(lz for (lz, ts, base_loads, base_prices) in base_data)
    time_series = unique_list(ts for (lz, ts, base_loads, base_prices) in base_data)
    # maybe this should use the hour of day from the model, but this is good enough for now
    hours_of_day = range(1, 1+len(base_data[0][2]))
    
    # create r arrays of base loads and prices, with indices = (hour of day, time series, load zone)
    base_loads = make_r_value_array(base_load_dict, hours_of_day, time_series, load_zones)
    base_prices = make_r_value_array(base_price_dict, hours_of_day, time_series, load_zones)
    
    # calibrate the demand system within R
    r.calibrate(base_loads, base_prices, dr_elasticity_scenario)


def bid(load_zone, time_series, prices):
    """Accept a vector of prices in a particular load_zone during a particular day (time_series).
    Return a tuple showing hourly load levels and willingness to pay for those loads."""
    
    bid = r.bid(str(load_zone), str(time_series), np.array(prices))
    demand = list(bid[0])
    wtp = bid[1][0] # everything is a vector in R, so we have to take the first element
    return (demand, wtp)


def test_calib():
    """Test calibration routines with sample data. Results should match r.test_calib()."""
    base_data = [
        ("oahu", 100, [ 500, 1000, 1500], [0.35, 0.35, 0.35]),
        ("oahu", 200, [2000, 2500, 3000], [0.35, 0.35, 0.35]),
        ("maui", 100, [3500, 4000, 4500], [0.35, 0.35, 0.35]),
        ("maui", 200, [5000, 5500, 6000], [0.35, 0.35, 0.35]),
    ]
    calibrate(base_data)
    r.print_calib()
    
    
def unique_list(seq):
    # from http://stackoverflow.com/questions/480214/how-do-you-remove-duplicates-from-a-list-in-python-whilst-preserving-order
    seen = set()
    return [x for x in seq if not (x in seen or seen.add(x))]

def make_r_value_array(base_value_dict, hours_of_day, time_series, load_zones):
    # create a numpy array with indices = (hour of day, time series, load zone)
    arr = np.array(
        [ [base_value_dict[(lz, ts)] for ts in time_series] for lz in load_zones],
        dtype=float
    ).transpose()
    # convert to an r array with dimnames, using R's standard array function
    # (it might be slightly neater to use rinterface to build r_array entirely
    # on the python side, but this is quick and well-documented since it uses
    # the standard R array constructor, with light translation to Python)
    # note: this uses automatic numpy <-> R conversion to pass the array and vectors to R
    r_array = r.array(
        arr,
        dim=np.array(arr.shape),
        dimnames=r.list(
            np.array(hours_of_day, dtype=str),
            np.array(time_series, dtype=str),
            np.array(load_zones, dtype=str)
        )
    )
    return r_array
    
# print "finished loading r_demand_system.py"