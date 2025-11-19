import json
import logging
import numpy as np
import random
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import argparse
from tqdm import tqdm

from ppm_construction.data_syn.grid_rules import (
    gen_circuit,
    TYPE_RESISTOR,
    TYPE_CAPACITOR,
    TYPE_INDUCTOR,
    TYPE_VOLTAGE_SOURCE,
    TYPE_CURRENT_SOURCE,
    TYPE_VCCS,
    TYPE_VCVS,
    TYPE_CCCS,
    TYPE_CCVS,
    TYPE_SHORT,
    MEAS_TYPE_VOLTAGE,
    MEAS_TYPE_CURRENT,
    TYPE_OPAMP_INVERTING,
    TYPE_OPAMP_NONINVERTING,
    TYPE_OPAMP_BUFFER,
    TYPE_OPAMP_INTEGRATOR,
    TYPE_OPAMP_DIFFERENTIATOR,
    TYPE_OPAMP_SUMMING,
)

logger = logging.getLogger(__name__)

# Thread-safe file write lock
file_write_lock = threading.Lock()


def compute_stat_info(circ):
    """Compute statistics dictionary for a circuit."""
    return {
        "num_nodes": len(circ.nodes),
        "num_branches": len(circ.branches),
        "num_resistors": len([1 for br in circ.branches if br['type'] == TYPE_RESISTOR]),
        "num_capacitors": len([1 for br in circ.branches if br['type'] == TYPE_CAPACITOR]),
        "num_inductors": len([1 for br in circ.branches if br['type'] == TYPE_INDUCTOR]),
        "num_voltage_sources": len([1 for br in circ.branches if br['type'] == TYPE_VOLTAGE_SOURCE]),
        "num_current_sources": len([1 for br in circ.branches if br['type'] == TYPE_CURRENT_SOURCE]),
        "num_controlled_sources": len([1 for br in circ.branches if br['type'] in [TYPE_VCCS, TYPE_VCVS, TYPE_CCCS, TYPE_CCVS]]),
        "num_shorts": len([1 for br in circ.branches if br['type'] == TYPE_SHORT]),
        "num_voltage_measurements": len([1 for br in circ.branches if br['type'] == TYPE_RESISTOR and br['measure'] == MEAS_TYPE_VOLTAGE]),
        "num_current_measurements": len([1 for br in circ.branches if br['type'] == TYPE_RESISTOR and br['measure'] == MEAS_TYPE_CURRENT]),
        "num_opamps": len([1 for br in circ.branches if br['type'] in [TYPE_OPAMP_INVERTING, TYPE_OPAMP_NONINVERTING, TYPE_OPAMP_BUFFER, TYPE_OPAMP_INTEGRATOR, TYPE_OPAMP_DIFFERENTIATOR, TYPE_OPAMP_SUMMING]]),
        "num_opamp_inverting": len([1 for br in circ.branches if br['type'] == TYPE_OPAMP_INVERTING]),
        "num_opamp_noninverting": len([1 for br in circ.branches if br['type'] == TYPE_OPAMP_NONINVERTING]),
        "num_opamp_buffer": len([1 for br in circ.branches if br['type'] == TYPE_OPAMP_BUFFER]),
        "num_opamp_integrator": len([1 for br in circ.branches if br['type'] == TYPE_OPAMP_INTEGRATOR]),
        "num_opamp_differentiator": len([1 for br in circ.branches if br['type'] == TYPE_OPAMP_DIFFERENTIATOR]),
        "num_opamp_summing": len([1 for br in circ.branches if br['type'] == TYPE_OPAMP_SUMMING]),
    }


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--note", type=str, default="v4")
    parser.add_argument("--gen_num", type=int, default=1000)
    parser.add_argument("--save_path", type=str, default="./data/grid/test.json")
    parser.add_argument("--num_proc", type=int, default=8)
    parser.add_argument("--symbolic", action="store_true", help="Generate symbolic circuits (component names instead of values)")
    parser.add_argument("--simple_circuits", action="store_true", help="Generate simpler circuits for faster equation analysis")
    parser.add_argument("--integrator", action="store_true", help="Guarantee exactly one integrator op-amp in each generated circuit")
    parser.add_argument("--no-meas", dest="no_meas", action="store_true", help="Hide all probe drawings except those required to control dependent sources")

    args = parser.parse_args()
    return args

def threading_task(task_id, seed, note, gen_num, save_path, symbolic=False, simple_circuits=False, integrator=False, no_meas=False):
    """Generate circuits in a thread-safe manner with retry limits."""
    np.random.seed(seed)
    random.seed(seed)
    cnt = 0
    skipped_count = 0
    max_retries = 20
    
    for i in tqdm(range(gen_num), desc=f"Task {task_id}"):
        circuit_id = f"{task_id}_{cnt+1}"
        retries = 0
        circ = None
        
        while retries < max_retries:
            try:
                circ = gen_circuit(note, id=circuit_id, symbolic=symbolic, simple_circuits=simple_circuits, integrator=integrator, no_meas=no_meas)
                if circ and circ.valid:
                    break
            except Exception as e:
                logger.debug(f"Error generating circuit {circuit_id} (attempt {retries + 1}): {e}")
            
            retries += 1
        
        if not circ or not circ.valid:
            logger.warning(f"Skipping circuit {circuit_id} after {max_retries} failed attempts")
            skipped_count += 1
            continue
        
        try:
            latex_code = circ.to_latex()
            spice_code = circ._to_SPICE()
        except Exception as e:
            logger.error(f"Error processing circuit {circuit_id}: {e}")
            skipped_count += 1
            continue
        
        stat_info = compute_stat_info(circ)
        
        # Thread-safe file writes
        with file_write_lock:
            txt_path = save_path.replace(".json", ".txt")
            with open(txt_path, "a+", encoding='utf-8') as file:
                file.write(f"{circuit_id} valid, Saving {circuit_id}...\n")
            
            with open(save_path, "a+", encoding='utf-8') as f:
                new_item = {
                    "id": circuit_id,
                    "latex": latex_code,
                    "spice": spice_code,
                    "stat": stat_info
                }
                f.write(json.dumps(new_item, ensure_ascii=False) + "\n")
        
        cnt += 1
    
    if skipped_count > 0:
        logger.warning(f"Task {task_id}: Skipped {skipped_count} circuits due to generation failures")
    
    return skipped_count

def main(args):
    """Main entry point for circuit generation."""
    note = args.note
    gen_num = args.gen_num
    save_path = args.save_path
    num_proc = args.num_proc
    symbolic = args.symbolic
    simple_circuits = args.simple_circuits
    integrator = args.integrator
    no_meas = args.no_meas

    # Initialize output file
    with open(save_path, "w", encoding='utf-8') as f:
        f.write("")

    total_skipped = 0
    
    with ThreadPoolExecutor(max_workers=num_proc) as executor:
        futures = []
        for i in range(1, num_proc+1):
            future = executor.submit(threading_task, i, i, note, gen_num // num_proc, save_path, symbolic, simple_circuits, integrator, no_meas)
            futures.append(future)
        
        # Collect skipped counts from all tasks
        for future in futures:
            try:
                skipped = future.result()
                total_skipped += skipped
            except Exception as e:
                logger.error(f"Task failed with exception: {e}")
    
    if total_skipped > 0:
        logger.warning(f"Total skipped circuits: {total_skipped}")
    else:
        logger.info("All circuits generated successfully")

def stat(args):
    """Compute and save statistics from generated circuit data."""
    save_path = Path(args.save_path)
    
    if not save_path.exists():
        logger.info("No data file found, skipping statistics")
        return
        
    with open(save_path, "r", encoding='utf-8') as f:
        lines = f.readlines()
        if not lines:
            logger.info("No data found, skipping statistics")
            return
        data = [json.loads(line) for line in lines if line.strip()]
    
    if not data:
        logger.info("No valid data found, skipping statistics")
        return
    
    stat_infos = {
        "num_nodes": [],
        "num_branches": [],
        "num_resistors": [],
        "num_capacitors": [],
        "num_inductors": [],
        "num_voltage_sources": [],
        "num_current_sources": [],
        "num_controlled_sources": [],
        "num_shorts": [],
        "num_voltage_measurements": [],
        "num_current_measurements": [],
        "num_opamps": [],
        "num_opamp_inverting": [],
        "num_opamp_noninverting": [],
        "num_opamp_buffer": [],
        "num_opamp_integrator": [],
        "num_opamp_differentiator": [],
        "num_opamp_summing": [],
    }
    stat_results = {
        "args": vars(args),
        "num_nodes": {},
        "num_branches": {},
        "num_resistors": {},
        "num_capacitors": {},
        "num_inductors": {},
        "num_voltage_sources": {},
        "num_current_sources": {},
        "num_controlled_sources": {},
        "num_shorts": {},
        "num_voltage_measurements": {},
        "num_current_measurements": {},
        "num_opamps": {},
        "num_opamp_inverting": {},
        "num_opamp_noninverting": {},
        "num_opamp_buffer": {},
        "num_opamp_integrator": {},
        "num_opamp_differentiator": {},
        "num_opamp_summing": {},
    }
    for item in data:
        stat_info = item["stat"]
        for key in stat_info:
            stat_infos[key].append(stat_info[key])
    
    for key in stat_infos:
        if len(stat_infos[key]) > 0:
            mmean = float(np.mean(stat_infos[key]))
            sstd = float(np.std(stat_infos[key]))
            mmax = float(np.max(stat_infos[key]))
            mmin = float(np.min(stat_infos[key]))
            
            logger.info(f"{key}: mean={mmean:.2f}, std={sstd:.2f}, max={mmax}, min={mmin}")

            stat_results[key] = {
                "mean": mmean,
                "std": sstd,
                "max": mmax,
                "min": mmin
            }
        else:
            logger.info(f"{key}: No data")
            stat_results[key] = {"mean": 0, "std": 0, "max": 0, "min": 0}
    
    stat_output_path = save_path.parent / (save_path.stem + "_stat.json")
    with open(stat_output_path, "w", encoding='utf-8') as f:
        f.write(json.dumps(stat_results, ensure_ascii=False, indent=4))
    logger.info(f"Statistics saved to {stat_output_path}")
    

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    args = parse_args()
    main(args)
    stat(args)