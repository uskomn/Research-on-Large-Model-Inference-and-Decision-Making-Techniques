from flask import Flask, request, jsonify
from flask_cors import CORS
import json
import datetime

app = Flask(__name__)
CORS(app)

# 医疗知识库
MEDICAL_KNOWLEDGE = {
    "emergency_levels": {
        "一级": "生命体征不稳定，需立即抢救",
        "二级": "生命体征不稳定，需紧急处理",
        "三级": "生命体征稳定，需尽快处理",
        "四级": "生命体征稳定，可延迟处理"
    },
    "symptoms": {
        "呼吸困难": {
            "相关疾病": ["心衰", "哮喘", "肺炎", "肺栓塞"],
            "处置建议": "立即检查呼吸频率、血氧饱和度，准备氧气"
        },
        "胸痛": {
            "相关疾病": ["心肌梗死", "肺栓塞", "主动脉夹层"],
            "处置建议": "进行心电图检查，监测生命体征"
        },
        "意识障碍": {
            "相关疾病": ["脑卒中", "颅内出血", "药物中毒"],
            "处置建议": "评估格拉斯哥昏迷评分，保持气道通畅"
        },
        "大出血": {
            "相关疾病": ["创伤", "消化道出血", "产后出血"],
            "处置建议": "立即止血，建立静脉通道，补充血容量"
        },
        "高热": {
            "相关疾病": ["感染", "炎症", "肿瘤热"],
            "处置建议": "物理降温，必要时药物降温，寻找感染源"
        }
    },
    "procedures": {
        "心肺复苏": {
            "适应症": "心跳骤停",
            "步骤": [
                "确认患者无反应和无正常呼吸",
                "启动急救系统",
                "开始胸外按压",
                "开放气道",
                "人工呼吸",
                "检查循环和呼吸"
            ]
        },
        "气管插管": {
            "适应症": "呼吸衰竭、气道保护",
            "步骤": [
                "预给氧气",
                "喉镜暴露声门",
                "插入气管导管",
                "确认导管位置",
                "固定导管"
            ]
        }
    }
}

# 知识图谱数据
KNOWLEDGE_GRAPH = {
    "nodes": [
        {"id": "重症伤员", "group": "root", "label": "重症伤员"},
        {"id": "呼吸系统", "group": "system", "label": "呼吸系统"},
        {"id": "心血管系统", "group": "system", "label": "心血管系统"},
        {"id": "神经系统", "group": "system", "label": "神经系统"},
        {"id": "创伤", "group": "cause", "label": "创伤"},
        {"id": "感染", "group": "cause", "label": "感染"},
        {"id": "心衰", "group": "disease", "label": "心衰"},
        {"id": "脑卒中", "group": "disease", "label": "脑卒中"},
        {"id": "呼吸困难", "group": "symptom", "label": "呼吸困难"},
        {"id": "胸痛", "group": "symptom", "label": "胸痛"},
        {"id": "意识障碍", "group": "symptom", "label": "意识障碍"},
        {"id": "机械通气", "group": "treatment", "label": "机械通气"},
        {"id": "药物治疗", "group": "treatment", "label": "药物治疗"},
        {"id": "手术", "group": "treatment", "label": "手术"}
    ],
    "links": [
        {"source": "重症伤员", "target": "呼吸系统", "value": 1},
        {"source": "重症伤员", "target": "心血管系统", "value": 1},
        {"source": "重症伤员", "target": "神经系统", "value": 1},
        {"source": "重症伤员", "target": "呼吸困难", "value": 1},
        {"source": "重症伤员", "target": "胸痛", "value": 1},
        {"source": "重症伤员", "target": "意识障碍", "value": 1},
        {"source": "呼吸系统", "target": "呼吸困难", "value": 3},
        {"source": "心血管系统", "target": "胸痛", "value": 3},
        {"source": "神经系统", "target": "意识障碍", "value": 3},
        {"source": "心衰", "target": "呼吸困难", "value": 2},
        {"source": "脑卒中", "target": "意识障碍", "value": 2},
        {"source": "呼吸困难", "target": "机械通气", "value": 1},
        {"source": "呼吸困难", "target": "药物治疗", "value": 1},
        {"source": "胸痛", "target": "药物治疗", "value": 1},
        {"source": "意识障碍", "target": "手术", "value": 1}
    ]
}

@app.route('/api/health', methods=['GET'])
def health_check():
    """健康检查"""
    return jsonify({"status": "healthy", "message": "重症伤员处置系统运行正常"})

@app.route('/api/chat', methods=['POST'])
def chat():
    """问答接口"""
    try:
        data = request.get_json()
        user_message = data.get('message', '').strip()
        
        if not user_message:
            return jsonify({"error": "消息不能为空"}), 400
        
        # 简单的问答逻辑
        response = process_user_message(user_message)
        
        return jsonify({
            "response": response,
            "timestamp": datetime.datetime.now().isoformat()
        })
        
    except Exception as e:
        return jsonify({"error": f"处理消息时出错: {str(e)}"}), 500

@app.route('/api/knowledge-graph', methods=['GET'])
def get_knowledge_graph():
    """获取知识图谱数据"""
    return jsonify(KNOWLEDGE_GRAPH)

@app.route('/api/knowledge/search', methods=['GET'])
def search_knowledge():
    """搜索知识库"""
    query = request.args.get('q', '').strip()
    
    if not query:
        return jsonify({"error": "搜索关键词不能为空"}), 400
    
    # 简单的搜索逻辑
    results = []
    for symptom, info in MEDICAL_KNOWLEDGE["symptoms"].items():
        if query in symptom:
            results.append({
                "type": "症状",
                "name": symptom,
                "details": info
            })
    
    for procedure, info in MEDICAL_KNOWLEDGE["procedures"].items():
        if query in procedure:
            results.append({
                "type": "处置流程",
                "name": procedure,
                "details": info
            })
    
    return jsonify({"results": results})

def process_user_message(message):
    """处理用户消息并返回响应"""
    message_lower = message.lower()
    
    # 关键词匹配
    keywords = {
        "呼吸": "呼吸困难",
        "胸痛": "胸痛", 
        "意识": "意识障碍",
        "出血": "大出血",
        "发热": "高热",
        "心跳": "心肺复苏",
        "插管": "气管插管"
    }
    
    for keyword, symptom in keywords.items():
        if keyword in message_lower:
            if symptom in MEDICAL_KNOWLEDGE["symptoms"]:
                info = MEDICAL_KNOWLEDGE["symptoms"][symptom]
                response = f"关于{symptom}的建议：\n\n"
                response += f"可能相关疾病：{', '.join(info['相关疾病'])}\n\n"
                response += f"处置建议：{info['处置建议']}\n\n"
                response += "⚠️ 请注意：此为参考建议，实际情况请咨询专业医疗人员"
                return response
    
    # 如果没有匹配到具体症状，返回一般性建议
    if any(word in message_lower for word in ["严重", "紧急", "危险", "急救"]):
        return ("紧急情况处理原则：\n\n"
                "1. 评估生命体征（呼吸、脉搏、血压、意识）\n"
                "2. 保持气道通畅\n"
                "3. 维持循环稳定\n"
                "4. 立即呼救专业医疗团队\n"
                "5. 做好详细记录\n\n"
                "如有具体症状，请描述详细症状获得更专业建议。")
    
    return ("我是一个重症伤员处置问答助手。\n\n"
            "您可以询问：\n"
            "• 症状相关问题（如呼吸困难、胸痛等）\n"
            "• 处置流程（如心肺复苏、气管插管等）\n"
            "• 紧急情况处理原则\n\n"
            "请描述您遇到的具体情况，我会尽力提供帮助。")

if __name__ == '__main__':
    print("启动重症伤员处置问答系统...")
    print("API地址: http://localhost:5000")
    print("接口文档:")
    print("- GET  /api/health - 健康检查")
    print("- POST /api/chat - 问答接口")
    print("- GET  /api/knowledge-graph - 获取知识图谱")
    print("- GET  /api/knowledge/search?q=关键词 - 搜索知识库")
    app.run(debug=True, host='0.0.0.0', port=5000)