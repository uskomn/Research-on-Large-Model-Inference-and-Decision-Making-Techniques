import json
import re
from neo4j import GraphDatabase
from typing import Dict, List, Any
from model.utils.readDocx import readDocx
import requests
import os


class MedicalKGBuilder:
    """医疗知识图谱构建器"""

    def __init__(self, neo4j_uri: str, neo4j_user: str, neo4j_password: str,
                 deepseek_api_key: str = None):
        """
        初始化
        Args:
            neo4j_uri: Neo4j数据库URI (例如: bolt://localhost:7687)
            neo4j_user: Neo4j用户名
            neo4j_password: Neo4j密码
            deepseek_api_key: DeepSeek API密钥
        """
        self.driver = GraphDatabase.driver(neo4j_uri, auth=(neo4j_user, neo4j_password))
        self.deepseek_api_key = deepseek_api_key or os.getenv('DEEPSEEK_API_KEY')
        self.deepseek_api_url = "https://api.deepseek.com/v1/chat/completions"

    def close(self):
        """关闭数据库连接"""
        self.driver.close()

    def extract_knowledge_from_text(self, text: str, chunk_size: int = 3000) -> Dict[str, Any]:
        """
        使用DeepSeek提取文本中的知识图谱结构(分批处理)
        Args:
            text: 医疗文档文本
            chunk_size: 每批处理的文本长度
        Returns:
            包含entities和relationships的字典
        """
        print("正在使用DeepSeek分析文档(分批处理)...")

        # 将文本分成多个块
        text_chunks = []
        for i in range(0, len(text), chunk_size):
            chunk = text[i:i + chunk_size]
            if chunk.strip():  # 跳过空块
                text_chunks.append(chunk)

        print(f"文档已分成 {len(text_chunks)} 批进行处理")

        all_entities = []
        all_relationships = []
        entity_id_counter = {}  # 用于生成全局唯一ID

        # 逐批处理
        for idx, chunk in enumerate(text_chunks):
            print(f"\n处理第 {idx + 1}/{len(text_chunks)} 批...")

            try:
                kg_chunk = self._extract_from_chunk(chunk, idx)

                # 重新分配ID以确保全局唯一
                kg_chunk = self._reassign_ids(kg_chunk, entity_id_counter)

                all_entities.extend(kg_chunk['entities'])
                all_relationships.extend(kg_chunk['relationships'])

                print(
                    f"✓ 第 {idx + 1} 批完成: {len(kg_chunk['entities'])} 个实体, {len(kg_chunk['relationships'])} 个关系")

            except Exception as e:
                print(f"✗ 第 {idx + 1} 批处理失败: {e}")
                print("跳过此批次,继续处理...")
                continue

        # 合并去重
        final_kg = self._merge_and_deduplicate({
            'entities': all_entities,
            'relationships': all_relationships
        })

        print(f"\n{'=' * 50}")
        print(f"✓ 全部处理完成!")
        print(f"  总实体数: {len(final_kg['entities'])}")
        print(f"  总关系数: {len(final_kg['relationships'])}")
        print(f"{'=' * 50}\n")

        return final_kg

    def _extract_from_chunk(self, text: str, batch_idx: int) -> Dict[str, Any]:
        """
        从单个文本块提取知识
        Args:
            text: 文本块
            batch_idx: 批次索引
        Returns:
            包含entities和relationships的字典
        """
        prompt = f"""请分析这份急危重伤病诊疗规范文档片段,提取关键实体和关系。

实体类型:
- Disease: 疾病/症状
- Treatment: 治疗措施  
- Examination: 检查项目
- Medication: 药物
- Department: 部门/科室
- VitalSign: 生命体征指标
- Complication: 并发症

关系类型:
- REQUIRES_TREATMENT: 需要治疗
- REQUIRES_EXAMINATION: 需要检查
- USES_MEDICATION: 使用药物
- BELONGS_TO_DEPARTMENT: 属于科室
- MONITORS_SIGN: 监测指标
- CAUSES_COMPLICATION: 引起并发症

输出JSON格式(使用简单的属性值):
{{
  "entities": [
    {{"id": "d1", "type": "Disease", "name": "心脏骤停", "properties": {{"category": "循环系统"}}}},
    {{"id": "t1", "type": "Treatment", "name": "心肺复苏", "properties": {{}}}}
  ],
  "relationships": [
    {{"from": "d1", "to": "t1", "type": "REQUIRES_TREATMENT", "properties": {{}}}}
  ]
}}

注意:
1. 只返回JSON,不要其他内容
2. ID使用简单格式: d1,d2,t1,t2,e1,e2,m1,m2等
3. properties可以为空对象{{}}

文档片段:
{text}
"""

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.deepseek_api_key}"
        }

        payload = {
            "model": "deepseek-chat",
            "messages": [
                {
                    "role": "system",
                    "content": "你是医疗知识图谱构建专家。必须返回严格的JSON格式。"
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "temperature": 0.1,
            "max_tokens": 3000,
            "response_format": {"type": "json_object"}
        }

        response = requests.post(self.deepseek_api_url, headers=headers, json=payload, timeout=120)
        response.raise_for_status()

        response_data = response.json()
        response_text = response_data['choices'][0]['message']['content']

        # 清理响应
        response_text = self._clean_json_response(response_text)

        # 解析JSON
        try:
            kg_data = json.loads(response_text)
        except json.JSONDecodeError as e:
            print(f"  JSON解析失败: {e}")
            # 保存错误响应
            error_file = f'error_batch_{batch_idx}.txt'
            with open(error_file, 'w', encoding='utf-8') as f:
                f.write(response_text)
            print(f"  错误响应已保存到: {error_file}")

            # 尝试修复
            response_text = self._fix_json_errors(response_text)
            kg_data = json.loads(response_text)

        # 验证结构
        if 'entities' not in kg_data:
            kg_data['entities'] = []
        if 'relationships' not in kg_data:
            kg_data['relationships'] = []

        return kg_data

    def _reassign_ids(self, kg_data: Dict, id_counter: Dict) -> Dict:
        """
        重新分配ID以确保全局唯一
        Args:
            kg_data: 知识图谱数据
            id_counter: ID计数器
        Returns:
            重新分配ID后的数据
        """
        id_mapping = {}  # 旧ID -> 新ID的映射

        for entity in kg_data['entities']:
            entity_type = entity['type']
            old_id = entity['id']

            # 根据类型生成前缀
            prefix_map = {
                'Disease': 'd',
                'Treatment': 't',
                'Examination': 'e',
                'Medication': 'm',
                'Department': 'dept',
                'VitalSign': 'v',
                'Complication': 'c'
            }
            prefix = prefix_map.get(entity_type, 'n')

            # 生成新ID
            if prefix not in id_counter:
                id_counter[prefix] = 0
            id_counter[prefix] += 1
            new_id = f"{prefix}{id_counter[prefix]}"

            id_mapping[old_id] = new_id
            entity['id'] = new_id

        # 更新关系中的ID引用
        for rel in kg_data['relationships']:
            if rel['from'] in id_mapping:
                rel['from'] = id_mapping[rel['from']]
            if rel['to'] in id_mapping:
                rel['to'] = id_mapping[rel['to']]

        return kg_data

    def _merge_and_deduplicate(self, kg_data: Dict) -> Dict:
        """
        合并并去重实体和关系
        Args:
            kg_data: 知识图谱数据
        Returns:
            去重后的数据
        """
        print("\n正在合并和去重...")

        # 去重实体 (基于name和type)
        unique_entities = {}
        entity_id_map = {}  # 旧ID -> 新ID的映射

        for entity in kg_data['entities']:
            key = (entity['type'], entity['name'])
            if key not in unique_entities:
                unique_entities[key] = entity
                entity_id_map[entity['id']] = entity['id']
            else:
                # 记录ID映射关系
                entity_id_map[entity['id']] = unique_entities[key]['id']

        # 更新关系中的ID引用
        for rel in kg_data['relationships']:
            if rel['from'] in entity_id_map:
                rel['from'] = entity_id_map[rel['from']]
            if rel['to'] in entity_id_map:
                rel['to'] = entity_id_map[rel['to']]

        # 去重关系
        unique_relationships = []
        seen_rels = set()

        for rel in kg_data['relationships']:
            # 确保引用的实体存在
            from_exists = any(e['id'] == rel['from'] for e in unique_entities.values())
            to_exists = any(e['id'] == rel['to'] for e in unique_entities.values())

            if not (from_exists and to_exists):
                continue

            rel_key = (rel['from'], rel['to'], rel['type'])
            if rel_key not in seen_rels:
                seen_rels.add(rel_key)
                unique_relationships.append(rel)

        result = {
            'entities': list(unique_entities.values()),
            'relationships': unique_relationships
        }

        print(f"去重完成: {len(result['entities'])} 个唯一实体, {len(result['relationships'])} 个唯一关系")

        return result

    def _clean_json_response(self, text: str) -> str:
        """清理JSON响应"""
        # 移除markdown代码块标记
        text = re.sub(r'```json\s*', '', text)
        text = re.sub(r'```\s*', '', text)
        text = text.strip()

        # 移除BOM
        if text.startswith('\ufeff'):
            text = text[1:]

        return text

    def _fix_json_errors(self, text: str) -> str:
        """尝试修复常见的JSON错误"""
        # 修复单引号
        text = text.replace("'", '"')

        # 修复尾随逗号
        text = re.sub(r',\s*}', '}', text)
        text = re.sub(r',\s*]', ']', text)

        # 修复未转义的引号
        # 这个比较复杂,只做基本处理

        return text

    def _ensure_unique_ids(self, kg_data: Dict) -> Dict:
        """确保实体ID唯一(保留用于向后兼容)"""
        return kg_data

    def create_constraints(self):
        """创建Neo4j约束和索引"""
        print("创建数据库约束和索引...")

        constraints = [
            "CREATE CONSTRAINT IF NOT EXISTS FOR (d:Disease) REQUIRE d.id IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (t:Treatment) REQUIRE t.id IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (e:Examination) REQUIRE e.id IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (m:Medication) REQUIRE m.id IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (d:Department) REQUIRE d.id IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (v:VitalSign) REQUIRE v.id IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (c:Complication) REQUIRE c.id IS UNIQUE"
        ]

        with self.driver.session() as session:
            for constraint in constraints:
                try:
                    session.run(constraint)
                except Exception as e:
                    print(f"约束创建警告: {e}")

    def create_entities(self, entities: List[Dict]):
        """创建实体节点"""
        print(f"创建{len(entities)}个实体节点...")

        with self.driver.session() as session:
            for entity in entities:
                entity_type = entity['type']
                entity_id = entity['id']
                entity_name = entity['name']
                properties = entity.get('properties', {})

                # 构建属性字符串
                props_str = ', '.join([f"{k}: ${k}" for k in properties.keys()])
                if props_str:
                    props_str = ', ' + props_str

                cypher = f"""
                MERGE (n:{entity_type} {{id: $id}})
                SET n.name = $name{props_str}
                """

                params = {
                    'id': entity_id,
                    'name': entity_name,
                    **properties
                }

                session.run(cypher, params)

        print("实体创建完成")

    def create_relationships(self, relationships: List[Dict]):
        """创建关系"""
        print(f"创建{len(relationships)}个关系...")

        with self.driver.session() as session:
            for rel in relationships:
                from_id = rel['from']
                to_id = rel['to']
                rel_type = rel['type']
                properties = rel.get('properties', {})

                # 构建属性字符串
                if properties:
                    props_str = '{' + ', '.join([f"{k}: ${k}" for k in properties.keys()]) + '}'
                else:
                    props_str = ''

                cypher = f"""
                MATCH (a {{id: $from_id}}), (b {{id: $to_id}})
                MERGE (a)-[r:{rel_type} {props_str}]->(b)
                """

                params = {
                    'from_id': from_id,
                    'to_id': to_id,
                    **properties
                }

                try:
                    session.run(cypher, params)
                except Exception as e:
                    print(f"关系创建警告: {from_id} -> {to_id}: {e}")

        print("关系创建完成")

    def build_knowledge_graph(self, document_text: str, chunk_size: int = 3000):
        """
        构建完整的知识图谱(分批处理)
        Args:
            document_text: 医疗文档文本
            chunk_size: 每批处理的文本长度(默认3000字符)
        """
        print("=" * 50)
        print("开始构建知识图谱(分批处理模式)")
        print("=" * 50)

        # 1. 提取知识(分批)
        kg_data = self.extract_knowledge_from_text(document_text, chunk_size)

        # 2. 创建约束
        self.create_constraints()

        # 3. 创建实体
        self.create_entities(kg_data['entities'])

        # 4. 创建关系
        self.create_relationships(kg_data['relationships'])

        print("=" * 50)
        print("知识图谱构建完成!")
        print("=" * 50)

        return kg_data

    def query_graph(self, cypher: str) -> List[Dict]:
        """
        查询图谱
        Args:
            cypher: Cypher查询语句
        Returns:
            查询结果列表
        """
        with self.driver.session() as session:
            result = session.run(cypher)
            return [record.data() for record in result]

    def get_statistics(self) -> Dict:
        """获取图谱统计信息"""
        stats = {}

        with self.driver.session() as session:
            # 统计各类型节点数量
            node_types = ['Disease', 'Treatment', 'Examination', 'Medication',
                          'Department', 'VitalSign', 'Complication']

            for node_type in node_types:
                result = session.run(f"MATCH (n:{node_type}) RETURN count(n) as count")
                stats[node_type] = result.single()['count']

            # 统计关系数量
            result = session.run("MATCH ()-[r]->() RETURN count(r) as count")
            stats['total_relationships'] = result.single()['count']

            # 统计总节点数
            result = session.run("MATCH (n) RETURN count(n) as count")
            stats['total_nodes'] = result.single()['count']

        return stats


def main():
    """主函数"""

    # 读取文档
    base_dir=os.path.dirname(os.path.abspath(__file__))
    text_dir=os.path.join(base_dir,"words/需要紧急救治的急危重伤病标准.docx")
    document_text=readDocx(text_dir)

    # Neo4j连接配置
    NEO4J_URI = "bolt://localhost:7687"
    NEO4J_USER = "neo4j"
    NEO4J_PASSWORD = "aqzdwsfneo"  # 请修改为你的密码

    # DeepSeek API密钥 (或通过环境变量 DEEPSEEK_API_KEY 设置)
    DEEPSEEK_API_KEY = "sk-8cbf10f456ae40aba1be330eaa3c2397"

    # 创建知识图谱构建器
    builder = MedicalKGBuilder(NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD, DEEPSEEK_API_KEY)

    try:
        # 构建知识图谱
        kg_data = builder.build_knowledge_graph(document_text)

        # 保存提取的数据到JSON文件
        with open('knowledge_graph.json', 'w', encoding='utf-8') as f:
            json.dump(kg_data, f, ensure_ascii=False, indent=2)
        print("\n知识图谱数据已保存到 knowledge_graph.json")

        # 获取统计信息
        print("\n图谱统计信息:")
        stats = builder.get_statistics()
        for key, value in stats.items():
            print(f"  {key}: {value}")

        # 示例查询
        print("\n示例查询 - 查找所有疾病:")
        diseases = builder.query_graph("MATCH (d:Disease) RETURN d.name as name LIMIT 10")
        for disease in diseases:
            print(f"  - {disease['name']}")

        print("\n示例查询 - 查找心脏骤停的治疗措施:")
        treatments = builder.query_graph("""
            MATCH (d:Disease {name: '心脏骤停'})-[:REQUIRES_TREATMENT]->(t:Treatment)
            RETURN t.name as treatment
        """)
        for treatment in treatments:
            print(f"  - {treatment['treatment']}")

    finally:
        builder.close()
        print("\n数据库连接已关闭")


if __name__ == "__main__":
    main()