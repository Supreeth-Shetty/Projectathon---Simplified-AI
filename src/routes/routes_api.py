from flask import Blueprint, request, jsonify,session
from src.constants.model_params import DecisionTreeRegressor_Params, LinearRegression_Params, Ridge_Params, Lasso_Params, ElasticNet_Params, RandomForestRegressor_Params, SVR_params, AdabootRegressor_Params, GradientBoostRegressor_Params
from src.utils.common.data_helper import load_data
from src.feature_engineering.feature_engineering_helper import FeatureEngineering
from src.utils.common.plotly_helper import PlotlyHelper
from src.preprocessing.preprocessing_helper import Preprocessing
import pandas as pd
import numpy as np

app_api = Blueprint('api', __name__)


"""[summary]
Api for feature engeenring
Returns:
    [type]: [description]
"""
@app_api.route('/api/feature_selection', methods=['POST'])
def fe_feature_selection():
    try:
        df = load_data()
        df_ = df.loc[:, df.columns != 'Label']
        method = request.json['method']
        d = {'success': True}

        if method == "Find Constant Features":
            threshold = request.json['threshold']
            high_variance_columns = FeatureEngineering.feature_selection(df_, 'Label', method,
                                                                         threshold=float(threshold))
            high_variance_columns = list(high_variance_columns)
            low_variance_columns = [col for col in df_.columns
                                    if col not in high_variance_columns]
            d['high_variance_columns'] = high_variance_columns
            d['low_variance_columns'] = list(low_variance_columns)

        elif method == "Mutual Info Classification" or method == "Extra Trees Classifier":
            df_ = FeatureEngineering.feature_selection(df_, df.loc[:, 'Label'], method)
            graph = PlotlyHelper.barplot(df_, 'Feature', 'Value')
            d['graph'] = graph

        elif method == "Correlation":
            graph = PlotlyHelper.heatmap(df)
            d['graph'] = graph

        elif method == "Forward Selection" or method == "Backward Elimination":
            n_features_to_select = request.json['n_features_to_select']
            columns = FeatureEngineering.feature_selection(df_, df.loc[:, 'Label'], method,
                                                           n_features_to_select=int(n_features_to_select))
            selected_columns = columns
            not_selected_columns = [col for col in df_.columns
                                    if col not in selected_columns]
            d['selected_columns'] = selected_columns
            d['not_selected_columns'] = list(not_selected_columns)

        return jsonify(d)

    except Exception as e:
        print(e)
        return jsonify({'success': False})


# APIS
@app_api.route('/api/missing-data', methods=['GET', 'POST'])
def missing_data():
    try:
        new_df = None
        df = load_data()
        selected_column = request.json['selected_column']
        method = request.json['method']
        if method == 'Mean' or method == 'Median' or method == 'Arbitrary Value' or method == 'Interpolate':
            before = {}
            after = {}
            list_ = list(df[~df.loc[:, selected_column].isnull()][selected_column])
            before['graph'] = PlotlyHelper.distplot(list_, selected_column)
            before['skewness'] = Preprocessing.find_skewness(list_)
            before['kurtosis'] = Preprocessing.find_kurtosis(list_)

            if method == 'Mean':
                new_df = Preprocessing.fill_numerical(df, 'Mean', [selected_column])
            elif method == 'Median':
                new_df = Preprocessing.fill_numerical(df, 'Median', [selected_column])
            elif method == 'Arbitrary Value':
                new_df = Preprocessing.fill_numerical(df, 'Median', [selected_column], request.json['Arbitrary_Value'])
            elif method == 'Interpolate':
                new_df = Preprocessing.fill_numerical(df, 'Interpolate', [selected_column], request.json['Interpolate'])
            else:
                pass

            new_list = list(new_df.loc[:, selected_column])

            after['graph'] = PlotlyHelper.distplot(new_list, selected_column)
            after['skewness'] = Preprocessing.find_skewness(new_list)
            after['kurtosis'] = Preprocessing.find_kurtosis(new_list)

            d = {
                'success': True,
                'before': before,
                'after': after
            }
            return jsonify(d)

        if method == 'Mode' or method == 'New Category' or method == 'Select Exist':
            before = {}
            after = {}
            df_counts = pd.DataFrame(df.groupby(selected_column).count()).reset_index(level=0)
            y = list(pd.DataFrame(df.groupby(selected_column).count()).reset_index(level=0).iloc[:, 1].values)
            pie_graphJSON = PlotlyHelper.pieplot(df_counts, names=selected_column, values=y, title='')
            before['graph'] = pie_graphJSON

            if method == 'Mode':
                df[selected_column] = Preprocessing.fill_categorical(df, 'Mode', selected_column)
                df_counts = pd.DataFrame(df.groupby(selected_column).count()).reset_index(level=0)
                y = list(pd.DataFrame(df.groupby(selected_column).count()).reset_index(level=0).iloc[:, 1].values)
                pie_graphJSON = PlotlyHelper.pieplot(df_counts, names=selected_column, values=y, title='')

                after['graph'] = pie_graphJSON
            elif method == 'New Category':
                df[selected_column] = Preprocessing.fill_categorical(df, 'New Category', selected_column,
                                                                     request.json['newcategory'])
                df_counts = pd.DataFrame(df.groupby(selected_column).count()).reset_index(level=0)
                y = list(pd.DataFrame(df.groupby(selected_column).count()).reset_index(level=0).iloc[:, 1].values)
                pie_graphJSON = PlotlyHelper.pieplot(df_counts, names=selected_column, values=y, title='')
                after['graph'] = pie_graphJSON

            elif method == 'Select Exist':
                df[selected_column] = Preprocessing.fill_categorical(df, 'New Category', selected_column,
                                                                     request.json['selectcategory'])
                df_counts = pd.DataFrame(df.groupby(selected_column).count()).reset_index(level=0)
                y = list(pd.DataFrame(df.groupby(selected_column).count()).reset_index(level=0).iloc[:, 1].values)
                pie_graphJSON = PlotlyHelper.pieplot(df_counts, names=selected_column, values=y, title='')

                after['graph'] = pie_graphJSON

            d = {
                'success': True,
                'before': before,
                'after': after
            }
            return jsonify(d)

    except Exception as e:
        print(e)
        return jsonify({'success': False})

    return "Hello World!"


@app_api.route('/api/encoding', methods=['GET', 'POST'])
def fe_encoding():
    try:
        df = load_data()
        encoding_type = request.json['encoding_type']
        columns = df.columns
        
        if session['target_column'] is not None:
            columns = list(df.columns[df.columns != session['target_column']])
                            
        d = {'success': True}
        df = df.loc[:, columns]
        if encoding_type == "Base N Encoder":
            df,_ = FeatureEngineering.encodings(df, columns, encoding_type, base=request.json['base'])
        elif encoding_type == "Target Encoder":
            df,_ = FeatureEngineering.encodings(df, columns, encoding_type, n_components=request.json['target'])
        elif encoding_type == "Hash Encoder":
            """This is remaining to handle"""
            df,_ = FeatureEngineering.encodings(df, columns, encoding_type, n_components=request.json['hash'])
        else:
            df,_ = FeatureEngineering.encodings(df, columns, encoding_type)
        data = df.head(200).to_html()
        d['data'] = data
        return jsonify(d)

    except Exception as e:
        print(e)
        return jsonify({'success': False,'error':str(e)})


@app_api.route('/api/pca', methods=['POST'])
def fe_pca():
    try:
        df = load_data()
        df_ = df.loc[:, df.columns != 'Label']
        df_, evr_ = FeatureEngineering.dimenstion_reduction(df_, len(df_.columns))
        d = {'success': True}

        df_evr = pd.DataFrame()
        df_evr['No of Components'] = np.arange(0, len(evr_)) + 1
        df_evr['Variance %'] = evr_.round(2)

        data = pd.DataFrame(df_, columns=[f"Col_{col + 1}" for col in np.arange(0, df_.shape[1])]).head(200).to_html()
        graph = PlotlyHelper.line(df_evr, 'No of Components', 'Variance %')

        d['data'] = data
        d['graph'] = graph
        d['no_pca'] = len(evr_)
        return jsonify(d)

    except Exception as e:
        print(e)
        return jsonify({'success': False})
    
    
@app_api.route('/api/get_params', methods=['POST'])
def get_params():
    try:
        model_name = request.json['model']
        d = {'success': True}
        if model_name=="LinearRegression":
            d['params']=LinearRegression_Params
        elif model_name=="DecisionTreeRegressor":
            d['params']=DecisionTreeRegressor_Params
        elif model_name=="RandomForestRegressor":
            d['params']=RandomForestRegressor_Params
        elif model_name=="SVR":
            d['params']=SVR_params
        elif model_name=="GradientBoostingRegressor":
            d['params']=GradientBoostRegressor_Params
        elif model_name=="AdaBoostRegressor":
            d['params']=AdabootRegressor_Params
        elif model_name=="Ridge":
            d['params']=Ridge_Params
        elif model_name=="Lasso":
            d['params']=Lasso_Params
        elif model_name=="ElasticNet":
            d['params']=ElasticNet_Params
        else:
            d['params']=None
        return jsonify(d)

    except Exception as e:
        print(e)
        return jsonify({'success': False})    
