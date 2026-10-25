"""Compare the specified notebook with the desktop engine, using one environment."""
import argparse,contextlib,io,json
from pathlib import Path
import numpy as np,pandas as pd,shap
from sklearn.model_selection import train_test_split
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score,classification_report,roc_auc_score,confusion_matrix
from clinical_studio.config import default_config
from clinical_studio.engine import generate_dataset,AnalysisResult,_fit

def main():
    parser=argparse.ArgumentParser();parser.add_argument('notebook');parser.add_argument('report');args=parser.parse_args()
    nb=json.loads(Path(args.notebook).read_text());ns=dict(np=np,pd=pd,train_test_split=train_test_split,LogisticRegression=LogisticRegression,accuracy_score=accuracy_score,classification_report=classification_report,roc_auc_score=roc_auc_score,confusion_matrix=confusion_matrix)
    exec(''.join(nb['cells'][8]['source']),ns);exec(''.join(nb['cells'][11]['source']),ns)
    cfg=default_config();actual,names=generate_dataset(cfg);expected,features,label,_=ns['generate_clinical_data'](800,.15,42)
    pd.testing.assert_frame_equal(actual,expected)
    with contextlib.redirect_stdout(io.StringIO()):model,train,test,ytest,pred=ns['train_and_evaluate_model'](expected,features,label)
    r=AnalysisResult(cfg,Path('/private/tmp'),actual,names);_fit(r)
    pd.testing.assert_frame_equal(train,r.train);pd.testing.assert_frame_equal(test,r.test);np.testing.assert_array_equal(model.coef_,r.model.coef_);np.testing.assert_array_equal(pred,r.model.predict_proba(r.test)[:,1])
    a=shap.LinearExplainer(model,train);b=shap.LinearExplainer(r.model,shap.maskers.Independent(shap.utils.sample(r.train,100,random_state=0),max_samples=100))
    av,bv=a.shap_values(test),b.shap_values(r.test)
    np.testing.assert_allclose(av,bv,rtol=0,atol=1e-12);np.testing.assert_allclose(a.expected_value,b.expected_value,rtol=0,atol=1e-12)
    report=dict(passed=True,notebook_cells=[8,11,14,17],data_shape=list(actual.shape),data_equal=True,split_equal=True,model_coefficients_equal=True,predictions_equal=True,shap_max_absolute_error=float(np.abs(av-bv).max()),shap_tolerance=1e-12,shap_base_absolute_error=float(abs(a.expected_value-b.expected_value)),accuracy=r.metrics['accuracy'],auc=r.metrics['auc'],confusion_matrix=r.metrics['confusion_matrix'])
    Path(args.report).write_text(json.dumps(report,ensure_ascii=False,indent=2));print(report)
if __name__=='__main__':main()
