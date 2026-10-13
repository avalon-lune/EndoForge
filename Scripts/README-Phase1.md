# LapTrainer 第一阶段测试包

本程序用于验证 UE5 与 SOFA 的软组织抓持、牵拉和释放交互。它是工程原型，组织参数尚未经过实物标定，不用于临床决策或能力认证。

## 启动

1. 完整解压到可写的本地目录，保留 Engine、LapTrainer、Physics 等文件夹。
2. 双击 `StartTrainer.cmd`。启动器会先运行本地 SOFA 物理服务，再打开 UE 窗口。
3. 等界面显示物理服务在线后开始操作。无需 UE 编辑器、Blender 或真实手术器械。
4. 按 F10 或关闭游戏窗口退出；启动器会清理本次启动的物理服务。

Windows x64 系统需要兼容的显卡驱动和 Microsoft Visual C++ 运行库。若提示缺少运行库，可运行包内 `Engine/Extras/Redist/en-us/vc_redist.x64.exe`。本测试包使用 DirectX 11。

请不要只启动 `LapTrainer.exe`：这样不会自动启动物理服务。请勿同时打开多个实例；本版本独占本机 TCP 端口 47321，并仅监听 127.0.0.1。

## 键鼠操作

| 操作 | 按键 |
|---|---|
| 在组织平面上移动钳尖 | 按住鼠标右键移动，或方向键 |
| 抬高 / 降低钳尖 | W / S，或鼠标滚轮 |
| 闭合并保持钳口 | 按住空格；松开空格释放 |
| 旋转夹钳 | Q / E |
| 加快移动 | 按住左 Shift |
| 重置训练 | R |
| 循环切换三个观察视角 | Tab |
| 显示 / 隐藏帮助 | H |
| 释放鼠标 | Esc；右键点击视口恢复 |
| 退出 | F10 |

## 第一次抓持

1. 启动或按 R 复位后，钳尖初始高度约 22 mm（2.2 cm），组织上表面高度约 12 mm（1.2 cm）。
2. 保持钳口张开，按 S 或向下滚动鼠标滚轮，将钳尖降到 12 mm 附近。
3. 这时再按住空格闭钳。看到界面显示抓持成功后，继续保持空格，按 W 抬高钳尖，观察组织牵拉变形。
4. 松开空格释放组织，观察回弹；按 R 可重置。Tab 可循环切换三个观察视角。

请先接近组织，再闭钳。若先按住空格再降低钳尖，近场捕获不会自动重试；需要松开空格，然后再次闭钳。

## 本阶段的物理范围

- 抓持使用以钳尖为中心、约 8 mm 近场范围的柔顺约束模型；尚未实现完整钳口表面的摩擦与碰撞求解。
- 组织由 SOFA 四面体 FEM 实时计算，当前重力关闭，材料参数尚未标定。
- 抓持后的安全牵拉行程上限为 35 mm，超过时将松脱，需要重新张开并闭合钳口抓取。
- 本版本不包含剪切、缝合、真实器械输入或主动力反馈。

## 日志与故障

- 启动器、SOFA 和 UE 日志位于包内 `Logs` 文件夹，按每次启动的时间分别保存。
- 若提示端口 47321 已被占用，先关闭之前的训练程序。启动器不会擅自终止其他进程。
- 若 SOFA 未就绪或异常退出，启动器会报错并保留日志；不要把静止画面视为物理模拟已成功。
- 如反馈问题，请提供操作步骤、截图和本次对应的日志。原型材料和指标仅用于工程调试。

## 自动验收入口

工具轨迹演示（AutoDemo）可在 PowerShell 中调用：

```powershell
& .\StartTrainer.ps1 -LapAutoDemo -LapAutoExit -LapCaptureDir 'C:\Temp\LapTrainerCaptures'
```

AutoDemo 直接驱动预定的工具轨迹，用于观察抓持、牵拉、释放和复位的 SOFA 物理结果，并保存阶段截图。

正常按键读取分支测试（KeyTest）：

```powershell
& .\StartTrainer.ps1 -LapKeyTest -LapAutoExit -LapCaptureDir 'C:\Temp\LapTrainerKeyTest'
```

KeyTest 经 UE PlayerController 注入输入事件，测试正常操作代码中的按键读取分支。每次选择一种模式；未传这两个模式参数时为普通手动操作。这两类自动验证都不等同于用户用实体键盘和鼠标完成的交互验收，也不证明临床有效性。

本测试包的结果文件和阶段截图入口为 [Verification 目录](Verification/)。运行复测时，新的截图会写入 `-LapCaptureDir` 指定目录，新的运行日志写入 `Logs`。

## 依赖与源码

- 图形与交互：Unreal Engine 5.7.4。
- 物理：SOFA 26.06.00，本地原生 C++ 服务，动态加载所需组件。
- 自研物理服务源码、依赖下载与构建脚本、依赖清单及网络测试随包放在 `Source/Physics`。
- UE 工程随包放在 `Source/LapTrainer`，包含 `.uproject`、`Config`、`Content`、`Source` 和 `Scripts`；不包含可重新生成的编译缓存。项目工作区内的原工程为 `Prototype/LapTrainer`。
- SOFA 对应版本源码包随包放在 `Source/Dependencies/sofa-v26.06.00-source.zip`；解压该源码包可查看上游实现和许可证。开发重建需要 UE 5.7.4、Visual Studio C++ 工具链及物理服务构建说明中的依赖，普通运行不需要安装这些开发工具。
- 随包第三方许可和声明见 `Licenses` 及 `Physics` 中的相关文件。SOFA 上游源码：https://github.com/sofa-framework/sofa/tree/v26.06.00 。
- `package-manifest.json` 记录组装时的文件大小与 SHA-256；运行后新增日志不包含在该清单内。
