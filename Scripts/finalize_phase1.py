"""Collect existing verification evidence, hash the deliverable and create its ZIP."""
from pathlib import Path
from datetime import datetime
import hashlib
import json
import shutil
import zipfile

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / 'output/Phase1/LapTrainer'
EVIDENCE = ROOT / 'output/verification'
VERIFY = PACKAGE / 'Verification'


def sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def main():
    physics = read_json(ROOT / 'Physics/runtime/physics-test-results.json')
    network = read_json(ROOT / 'Physics/runtime/network-test-results.json')
    keyboard = read_json(EVIDENCE / 'packaged-key-input/key-input-test.json')
    auto_log = (EVIDENCE / 'packaged-integration/trainer.log').read_text(encoding='utf-8-sig')
    assert physics['passed'] and network['passed'] and keyboard['passed'], 'A regression report failed'
    assert 'LAP_AUTODEMO complete. Requesting exit.' in auto_log
    assert '02_grasp.png grasp=1' in auto_log and '04_release.png grasp=0' in auto_log
    assert 'BUILD SUCCESSFUL' in (ROOT / 'Prototype/LapTrainer/Saved/Logs/Package-final.log').read_text(encoding='utf-8-sig')
    screenshots = [EVIDENCE / 'packaged-integration' / name for name in
                   ('01_initial.png', '02_grasp.png', '03_traction.png', '04_release.png', '05_reset.png')]
    screenshots.append(EVIDENCE / 'packaged-key-input/06_key_input_overview.png')
    assert all(p.is_file() and p.stat().st_size > 10000 for p in screenshots)
    VERIFY.mkdir(parents=True, exist_ok=True)
    for path in screenshots:
        shutil.copy2(path, VERIFY / path.name)
    for path in (ROOT / 'Physics/runtime/physics-test-results.json',
                 ROOT / 'Physics/runtime/network-test-results.json',
                 EVIDENCE / 'packaged-key-input/key-input-test.json'):
        shutil.copy2(path, VERIFY / path.name)
    shutil.copy2(EVIDENCE / 'packaged-integration/trainer.log', VERIFY / 'packaged-auto-demo.log')
    shutil.copy2(EVIDENCE / 'packaged-key-input/trainer.log', VERIFY / 'packaged-key-input.log')
    summary = {
        'assembled_at': datetime.now().astimezone().isoformat(),
        'engine': 'Unreal Engine 5.7.4', 'physics': 'SOFA 26.06.00',
        'platform': 'Windows x64, DirectX 11, Development build',
        'physics_regression_passed': physics['passed'],
        'network_regression_passed': network['passed'],
        'packaged_keyboard_integration_passed': keyboard['passed'],
        'packaged_visual_sequence_completed': True,
        'screenshots': [p.name for p in screenshots],
        'physics_exe_sha256': sha256(PACKAGE / 'Physics/LapPhysics.exe'),
        'game_exe_sha256': sha256(PACKAGE / 'LapTrainer/Binaries/Win64/LapTrainer.exe'),
        'limitations': [
            'Uncalibrated material and force values; no clinical validation.',
            'Near-field compliant grasp; no complete jaw-surface friction/contact solver.',
            'Gravity disabled; fixed tissue edge; no cutting, suturing or haptics.',
            'Automated keyboard integration is not a physical mouse hardware test.',
            'The visual sequence was captured before the final keyboard-test-only code addition.'
        ]
    }
    (VERIFY / 'verification-summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    report = f'''# 第一阶段交付验证记录

本包已在当前电脑通过 UE 5.7.4 的 Windows 独立打包运行。运行入口为根目录 `StartTrainer.cmd`。

| 检查 | 结果与证据 |
|---|---|
| UE 编译与 Windows 打包 | 成功；最终游戏程序 SHA-256 见 verification-summary.json |
| SOFA 数值回归 | 通过；静止、抓持、牵拉、释放、复位、反复极限操作、超行程释放 |
| 本机 TCP 协议 | 通过；异常消息拒绝、超时释放、重连、10 次复位、过大消息断开 |
| 独立打包版轨迹与画面 | 完成；01–05 截图依次为初始、抓持、牵拉、释放、复位 |
| 最终打包版键盘输入链路 | 通过；S 下降、空格抓持、W 牵拉、松开空格释放、R 复位、Tab 切视角 |

键盘测试通过 PlayerController 的 InputKey 注入事件，由正常交互代码读取，未直接写入钳尖位置。测试最低钳尖高度 {keyboard['min_tip_height_cm']:.3f} cm、最高持物高度 {keyboard['max_held_tip_height_cm']:.3f} cm、峰值模型反力 {keyboard['peak_force_n']:.3f} N。数值仅用于检查响应。

SOFA 网格为 {physics['node_count']} 个节点、{physics['tetrahedron_count']} 个四面体、{physics['surface_triangle_count']} 个表面三角形。数值回归求解耗时 P95 为 {physics['step_p95_ms']:.2f} ms，最大值 {physics['step_max_ms']:.2f} ms；这是本机这次测试的结果，不是其他硬件上的性能承诺。

## 你可以开始的手动测试

1. 双击 StartTrainer.cmd，等待 PHYSICS CONNECTED。
2. 按 S 或下滚轮，把钳尖从 22 mm 降至组织表面约 12 mm。
3. 按住空格夹住组织，同时按 W 抬升；随后松开空格，观察回弹。
4. 按住鼠标右键移动钳尖；Q/E 旋转，Tab 查看其他视角，R 复位，F10 退出。

真实鼠标手感与医生使用反馈仍由这次人工试用确认。自动测试不等于医学有效性验证。

## 当前范围

本版使用 SOFA 共旋转四面体有限元。抓持为 8 mm 近场柔顺约束，超出 35 mm 牵拉行程会松脱。当前关闭重力，固定组织后缘，材料未做实物标定；尚无完整钳口摩擦碰撞、剪切、缝合和力反馈。

01–05 画面由加入键盘测试模式前的打包版生成；最终版只新增独立测试入口，材质、场景和求解器未变。06 截图及 key-input-test.json 来自最终打包版。完整判定与哈希见各 JSON 文件，游戏测试日志同时保留在本目录。
'''
    (VERIFY / '验证记录.md').write_text(report, encoding='utf-8')
    files = []
    for path in sorted(PACKAGE.rglob('*')):
        if not path.is_file():
            continue
        rel = path.relative_to(PACKAGE)
        if rel.name == 'package-manifest.json' or rel.suffix.lower() == '.pdb':
            continue
        if rel.parts[0] == 'Logs' or rel.parts[:2] == ('LapTrainer', 'Saved'):
            continue
        files.append(path)
    manifest = [{'path': p.relative_to(PACKAGE).as_posix(), 'bytes': p.stat().st_size, 'sha256': sha256(p)} for p in files]
    manifest_path = PACKAGE / 'package-manifest.json'
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    files.append(manifest_path)
    zip_path = PACKAGE.parent / 'LapTrainer_Phase1_Win64.zip'
    with zipfile.ZipFile(zip_path, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=5, allowZip64=True) as archive:
        for path in files:
            archive.write(path, 'LapTrainer/' + path.relative_to(PACKAGE).as_posix())
    with zipfile.ZipFile(zip_path) as archive:
        bad = archive.testzip()
        assert bad is None, f'ZIP CRC failure: {bad}'
    digest = sha256(zip_path)
    (zip_path.parent / (zip_path.name + '.sha256')).write_text(f'{digest}  {zip_path.name}\n', encoding='ascii')
    print(json.dumps({'zip': str(zip_path), 'files': len(files), 'uncompressed_bytes': sum(p.stat().st_size for p in files),
                      'zip_bytes': zip_path.stat().st_size, 'sha256': digest, 'zip_crc_passed': True}, indent=2))


if __name__ == '__main__':
    main()
