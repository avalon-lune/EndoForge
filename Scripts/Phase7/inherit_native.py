"""Verify exact immutable physics inputs before reusing Phase 6 native evidence.

This is evidence inheritance, never a claim that a Phase 7 native suite was run.
Changed physics bytes require new regression; current UE/package traces and image
audits remain mandatory even when inheritance passes.
"""
import argparse
from pathlib import Path
from common import read, require, sha, write_new


def verify(root, native_suite):
    baseline = root/'output/Phase6/EndoForge-20261024-r2/phase6-build-receipt.json'
    delivery = root/'output/Phase6/phase6-final-verification.json'
    build, final, suite = read(baseline), read(delivery), read(native_suite)
    sealed_suite = root/'output/Phase6/EndoForge-20261024-r2/Verification/Reports/native.json'
    require(sha(native_suite) == sha(sealed_suite), 'Native suite differs from the sealed accepted Phase6 report')
    require(final['passed'] is True and suite['passed'] is True, 'Prior acceptance is incomplete')
    require(suite['checks']['thirty_five_native_cases'] is True, 'Missing full native suite')
    require(suite['checks']['fifteen_long_hold_cases_and_all_raw_states'] is True, 'Missing sustained holds')
    binary = sha(root/'Physics/runtime/LapPhysics.exe')
    require(binary == build['physics_exe_sha256'] == final['physics_exe_sha256'] == suite['native_binary']['sha256'], 'Changed native binary requires requalification')
    asset = sha(root/'Assets/Phase7/physics-mesh.json')
    require(asset == sha(root/'Assets/Phase6/physics-mesh.json') == suite['anatomy_asset']['sha256'] == final['physics_asset_sha256'], 'Changed physical asset requires requalification')
    inputs = {k:v for k,v in build['source_asset_sha256'].items() if k.startswith('Physics/')}
    require(inputs and all(sha(root/k) == v for k,v in inputs.items()), 'Native source/tool inputs changed')
    sealed_package = root/'output/Phase6/EndoForge-20261024-r2'
    manifest = read(sealed_package/'package-manifest.json')
    runtime_inputs = {item['path'][len('Physics/'):]:item['sha256'] for item in manifest if item['path'].startswith('Physics/')}
    require(runtime_inputs and all(sha(root/'Physics/runtime'/name) == digest for name,digest in runtime_inputs.items()),
            'Native runtime dependency/configuration differs from sealed Phase6; requalification required')
    return {'schema':'endoforge.phase7.native-inheritance.v1','phase':7,'passed':True,
            'execution_phase':6,'native_suite_reexecuted':False,
            'native_binary_sha256':binary,'physical_asset_sha256':asset,
            'native_input_count':len(inputs),'native_inputs_sha256':inputs,
            'runtime_dependency_count':len(runtime_inputs),'runtime_dependencies_sha256':runtime_inputs,
            'native_suite':{'path':str(native_suite.resolve()),'sha256':sha(native_suite)},
            'sealed_phase6_native_report_sha256':sha(sealed_suite),
            'baseline_build_receipt_sha256':sha(baseline),'prior_delivery_receipt_sha256':sha(delivery),
            'scope':'Inherited exact-binary/physical-asset Phase6 regression evidence. Fresh Phase7 UE, packaged interaction, collision, rendering and data audits are separate mandatory gates.'}


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',type=Path,required=True)
    p.add_argument('--native-suite',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();result=verify(a.root.resolve(),a.native_suite)
    write_new(a.output,result)
    print('Verified exact native inheritance; no new native execution claimed.')
