"""Debug utilities for circuit analysis (internal use only)."""

from lcapy import Circuit, mna


def debug_mna_object(netlist_string):
    """Debug helper to inspect MNA object structure (internal use only).
    
    Args:
        netlist_string: SPICE netlist string
    
    Returns:
        Tuple of (matrix_eqs, mna_obj) or (None, None) on failure
    """
    try:
        print("=== DEBUG MNA OBJECT ===")
        circuit = Circuit(netlist_string)
        print(f"Circuit created successfully")
        
        circuit_s = circuit.laplace()
        print(f"Laplace transform applied")
        
        mna_obj = mna.MNA(circuit_s, solver_method='scipy')
        print(f"MNA object created with scipy solver")
        
        matrix_eqs = mna_obj.matrix_equations()
        print(f"Matrix equations obtained: {type(matrix_eqs)}")
        
        print(f"\nMNA object attributes:")
        for attr in sorted(dir(mna_obj)):
            if not attr.startswith('_'):
                try:
                    value = getattr(mna_obj, attr)
                    print(f"  {attr}: {type(value)} = {str(value)[:100]}...")
                except:
                    print(f"  {attr}: <access_error>")
        
        print(f"\nMatrix equations attributes:")
        for attr in sorted(dir(matrix_eqs)):
            if not attr.startswith('_'):
                try:
                    value = getattr(matrix_eqs, attr)
                    print(f"  {attr}: {type(value)}")
                except:
                    print(f"  {attr}: <access_error>")
        
        print(f"\nBasic matrix representation:")
        print(str(matrix_eqs))
        
        return matrix_eqs, mna_obj
        
    except Exception as e:
        print(f"Debug failed: {e}")
        import traceback
        traceback.print_exc()
        return None, None

