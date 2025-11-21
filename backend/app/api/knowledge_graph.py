from flask import Blueprint,jsonify,request

kg_bp=Blueprint('knowledge_graph',__name__)

@kg_bp.route('/get_kg',methods=['GET'])
def get_kg():
    return jsonify("知识图谱")