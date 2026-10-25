"""独立读取导出的 SVG，核对颜色、内嵌字体轮廓和真实描边宽度。"""
import argparse
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET

COLOR_KEYS={
    "summary":["low_color","high_color"],"bar":["bar_color"],
    "force":["positive_color","negative_color"],"waterfall":["positive_color","negative_color"],
    "dependence_protective":["point_color"],"dependence_risk":["point_color"],
}


def inspect(directory):
    directory=Path(directory)
    ui=json.loads((directory/"ui_verification.json").read_text(encoding="utf-8"))
    settings=ui["settings"];folder=Path(ui["result_folder"]);checks=[]
    for name,overrides in settings["plots"]["plots"].items():
        style={**settings["plots"]["common"],**overrides}
        file=folder/"figures"/(style["filename"]+".svg")
        text=file.read_text(encoding="utf-8");root=ET.fromstring(text)
        strokes=[];painted=[]
        for element in root.iter():
            props=dict(re.findall(r"([\w-]+)\s*:\s*([^;]+)",element.attrib.get("style","")))
            props.update({key:element.attrib[key] for key in ["fill","stroke","stroke-width"] if key in element.attrib})
            if props.get("stroke","none").strip()!="none":
                width=float(props.get("stroke-width","1"));strokes.append(width)
                painted.append(dict(fill=props.get("fill","").strip().lower(),stroke=props["stroke"].strip().lower(),width=width))
        required={"axis_width":style["axis_width"]}
        if name in ("force","waterfall"):required["line_width"]=style["line_width"]
        if name in ("summary","waterfall","dependence_protective","dependence_risk"):required["baseline_width"]=style["baseline_width"]
        matches={key:any(abs(value-width)<1e-6 for width in strokes) for key,value in required.items()}
        if name in ("bar","force","waterfall"):
            colors=[style["bar_color"]] if name=="bar" else [style["positive_color"],style["negative_color"]]
            matches["edge_width"]=all(any(item["fill"]==color.lower() and item["stroke"]==color.lower() and
                abs(item["width"]-style["edge_width"])<1e-6 for item in painted) for color in colors)
        expected_colors={key:style[key] for key in COLOR_KEYS[name]}
        color_matches={key:color.lower() in text.lower() for key,color in expected_colors.items()}
        # 只检查字体轮廓 ID，避免图中文字碰巧含有字体名造成误判。
        glyphs=[element.attrib.get("id","") for element in root.iter() if element.tag.endswith("path")]
        family=style["font_family"][0]
        normalized=re.sub(r"[\s_-]","",family).lower()
        font_match=any(normalized in re.sub(r"[\s_-]","",glyph).lower() for glyph in glyphs)
        checks.append(dict(graph=name,passed=all(matches.values()) and all(color_matches.values()) and font_match,
            primary_font=family,font_glyphs_in_svg=font_match,expected_widths=required,edge_width=style["edge_width"],
            observed_svg_stroke_widths=sorted(set(strokes)),width_matches=matches,colors=expected_colors,color_matches=color_matches))
    report=dict(passed=ui["passed"] and all(check["passed"] for check in checks),
                method="Independently parse exported SVG paths/styles; implicit stroke-width=1 is SVG default.",checks=checks)
    (directory/"svg_export_verification.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    return report


if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("directory");args=parser.parse_args()
    report=inspect(args.directory)
    for item in report["checks"]:print(item["graph"],"PASS" if item["passed"] else "FAIL",item["width_matches"])
    raise SystemExit(0 if report["passed"] else 1)
