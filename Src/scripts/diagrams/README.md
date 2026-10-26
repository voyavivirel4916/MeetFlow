# T03设计图导出

图源位于[Docs/diagrams/t03](../../../Docs/diagrams/t03/index.html)，索引为`catalog.json`。工具仅用于文档导出，不属于产品运行依赖。

安装绘图依赖（已锁定Mermaid 12.2.0）：

```powershell
cd Src/scripts/diagrams
npm ci --ignore-scripts
cd ../../..
```

导出需本机Chrome及Playwright。已有Playwright时指定包目录：

```powershell
$env:PLAYWRIGHT_MODULE_PATH = '你的Playwright包目录'
node Src/scripts/diagrams/render.mjs
node Src/scripts/diagrams/verify_gallery.mjs
python -m unittest discover -s Src/scripts -p "test_*.py"
```

脚本启动临时本机服务加载安装的Mermaid，在Chrome中逐图解析；错误直接失败，不用占位图代替。导出目录为`Docs/images/t03`，包含SVG、PNG和哈希清单；同时更新静态图集HTML。查看图集不需要Node、Chrome自动化或外网。

渲染依赖与产品依赖分开锁定。SVG经过XML序列化，可独立打开；图片带中文字体名称，PNG已固化字体供报告使用。SVG在未安装中文字体的设备上可能替换字体，优先插入PNG或在最终文档导出前检查。
