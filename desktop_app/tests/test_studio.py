"""数值兼容、全参数界面往返及导出集成验证。"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("MPLCONFIGDIR", "/private/tmp/dbq-matplotlib-check")
os.environ.setdefault("NUMBA_CACHE_DIR", "/private/tmp/dbq-numba")
import json
from pathlib import Path
import tempfile
import unittest
from copy import deepcopy
import numpy as np
import pandas as pd
from PySide6.QtCore import Qt

from clinical_studio.config import ROOT, default_config, validate, save_config, load_config
from clinical_studio.engine import generate_dataset, run_analysis, _fit, AnalysisResult
from clinical_studio.app import create_application, MainWindow
from clinical_studio.widgets import ValueField

APP = create_application([])


class NumericalTests(unittest.TestCase):
    def test_defaults_match_notebook_data_and_model(self):
        notebook = ROOT.parent.parent / "260607_丁冰倩_虚拟数据生成和shap分析.ipynb"
        if notebook.is_file():
            nb = json.loads(notebook.read_text())
            ns = dict(np=np, pd=pd)
            exec("".join(nb["cells"][8]["source"]), ns)
            expected, features, label, _ = ns["generate_clinical_data"](800, .15, 42)
        else:
            expected=pd.read_csv(Path(__file__).parent/"baseline_default_data.csv")
            features=list(expected.columns[1:-1])
        config = default_config(); actual, names = generate_dataset(config)
        pd.testing.assert_frame_equal(actual, expected)
        self.assertEqual(names, features)
        with tempfile.TemporaryDirectory() as directory:
            result = AnalysisResult(config, Path(directory), actual, names)
            _fit(result)
            self.assertAlmostEqual(result.metrics["accuracy"], .9375, places=10)
            self.assertAlmostEqual(result.metrics["auc"], .9522058823529412, places=10)
            self.assertEqual(result.metrics["confusion_matrix"], [[200,4],[11,25]])

    def test_all_distribution_controls_and_metadata(self):
        config = default_config(); data=config["data"]
        data.update(n_samples=120, positive_rate=.25, random_seed=123, id_prefix="ID-", id_width=6, id_start=9, id_name="编号", label_name="结果")
        for feature in data["features"]:
            if feature["kind"]=="continuous":
                feature.update(transform="round", digits=3)
                feature["positive"].update(mean=9.87654,std=0.,min=9.,max=11.)
                feature["negative"].update(mean=-2.34567,std=0.,min=-4.,max=-1.)
            else: feature.update(values=[2,5],positive_p=1.,negative_p=0.)
        validate(config); frame,names=generate_dataset(config)
        self.assertEqual(frame.shape,(120,9)); self.assertEqual(frame["结果"].sum(),30)
        self.assertEqual(frame["编号"].iloc[0],"ID-000009")
        for name in names[:-1]:
            self.assertTrue((frame.loc[frame["结果"]==1,name]==9.877).all())
            self.assertTrue((frame.loc[frame["结果"]==0,name]==-2.346).all())
        self.assertTrue((frame.loc[frame["结果"]==1,names[-1]]==5).all())
        self.assertTrue((frame.loc[frame["结果"]==0,names[-1]]==2).all())

    def test_reject_invalid_settings(self):
        for mutation in [lambda c:c["data"].update(positive_rate=0),
                         lambda c:c["data"]["features"][0]["positive"].update(std=-1),
                         lambda c:c["data"]["features"][0]["negative"].update(min=110,max=100),
                         lambda c:c["plots"]["plots"]["bar"].update(filename="../bad"),
                         lambda c:c["model"].update(penalty="elasticnet",solver="lbfgs")]:
            config=default_config(); mutation(config)
            with self.assertRaises(ValueError):validate(config)


class GuiTests(unittest.TestCase):
    def setUp(self):
        self.window=MainWindow(output=str(ROOT.parent/"verification"/"gui")); self.window.show(); APP.processEvents()
    def tearDown(self):self.window.close(); self.window.deleteLater(); APP.processEvents()

    def test_full_config_roundtrip_and_every_style_field_exposed(self):
        original=default_config()
        actual=self.window.collect_config()
        self.assertEqual(actual,original)
        pd.testing.assert_frame_equal(generate_dataset(actual)[0],generate_dataset(original)[0])
        for index in range(7):
            self.window.style_editor.selector.setCurrentIndex(index)
            fields=self.window.style_editor.fields
            self.assertTrue(set(original["plots"]["common"]).issubset(fields))
            self.window.style_editor.commit()
        self.assertEqual(self.window.collect_config(),original)

    def test_ui_data_edits_are_collected(self):
        editor=self.window.data_editor
        editor.general.fields["n_samples"].editor.setValue(150)
        editor.detail_forms["positive"].fields["mean"].editor.setValue(-12.5)
        editor.detail_forms["negative"].fields["std"].editor.setValue(7.25)
        editor.detail_forms["processing"].fields["digits"].editor.setValue(4)
        result=self.window.collect_config()
        self.assertEqual(result["data"]["n_samples"],150)
        self.assertEqual(result["data"]["features"][0]["positive"]["mean"],-12.5)
        self.assertEqual(result["data"]["features"][0]["negative"]["std"],7.25)
        self.assertEqual(result["data"]["features"][0]["digits"],4)
        editor.add_feature("binary"); self.assertEqual(len(editor.data["features"]),8)
        editor.remove_feature(); self.assertEqual(len(editor.data["features"]),7)

    def test_every_feature_parameter_roundtrip_and_reorder(self):
        editor=self.window.data_editor
        for index in range(7):
            editor.list.setCurrentRow(index)
            editor.commit_feature()
        actual=self.window.collect_config()
        self.assertEqual(actual,default_config())
        pd.testing.assert_frame_equal(generate_dataset(actual)[0],generate_dataset(default_config())[0])
        editor.move_feature(-1)
        self.assertEqual(editor.current,5)
        self.assertEqual(editor.data["features"][5]["name"],"高血压史")

    def test_per_plot_override_and_config_export(self):
        editor=self.window.style_editor
        editor.fields["axis_width"].editor.setValue(2.4)
        editor.selector.setCurrentIndex(3)  # force
        editor.overrides["positive_color"].setChecked(True)
        editor.fields["positive_color"].editor.text.setText("#F28E2B")
        editor.overrides["font_size"].setChecked(True)
        editor.fields["font_size"].editor.setValue(17)
        config=self.window.collect_config()
        self.assertEqual(config["plots"]["common"]["axis_width"],2.4)
        self.assertEqual(config["plots"]["plots"]["force"]["positive_color"],"#F28E2B")
        self.assertEqual(config["plots"]["plots"]["force"]["font_size"],17)
        self.assertNotIn("positive_color",config["plots"]["plots"]["bar"])
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"parameters.json";save_config(config,path)
            self.assertEqual(load_config(path),config)


class ExportTests(unittest.TestCase):
    def test_custom_render_and_redraw(self):
        config=default_config(); config["plots"].update(dpi=100,formats=["png","svg","pdf"])
        config["plots"]["common"].update(positive_color="#F28E2B",negative_color="#9467BD",
            bar_color="#258B68",low_color="#3A7D44",high_color="#C84472",line_width=2.2,axis_width=1.8,
            point_alpha=1.,baseline_color="#007F8B",font_size=13)
        config["plots"]["plots"]["force"]["positive_color"]="#C45511"
        config["plots"]["plots"]["waterfall"]["negative_color"]="#3955BB"
        output=ROOT.parent/"verification"/"custom"
        result=run_analysis(config,output)
        self.assertEqual(len(result.images),18)
        self.assertTrue(all(path.is_file() and path.stat().st_size>100 for path in result.images))
        self.assertTrue(all(a["passed"] for a in result.audit.values()))
        with pd.ExcelFile(result.folder/"analysis_results.xlsx") as book:
            self.assertEqual(len(book.sheet_names),5)
        self.assertTrue((result.folder/"shap_values.csv").is_file())
        self.assertAlmostEqual(result.metrics["auc"],.9522058823529412,places=10)
        redraw=deepcopy(config)
        for name,style in redraw["plots"]["plots"].items():style["enabled"]=name=="dependence_protective"
        redraw["plots"]["plots"]["dependence_protective"].update(interaction_feature="年龄")
        redraw["plots"]["formats"]=["png"]
        second=run_analysis(redraw,output,previous=result)
        self.assertEqual(len(second.images),1)
        self.assertIs(second.model,result.model)
        self.assertTrue(all(a["passed"] for a in second.audit.values()))
        self.assertNotEqual(result.folder,second.folder)
        invalid=deepcopy(redraw);invalid["data"]["random_seed"]=9
        with self.assertRaises(ValueError):run_analysis(invalid,output,previous=result)


if __name__=="__main__":unittest.main()
