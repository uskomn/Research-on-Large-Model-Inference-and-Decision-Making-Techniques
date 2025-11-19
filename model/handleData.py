import json
import re
from neo4j import GraphDatabase
from typing import Dict, List, Any
from model.utils.readDocx import readDocx
import requests
import os


class MedicalKGBuilder:
    def __init__(self, neo4j_uri: str, neo4j_user: str, neo4j_password: str,
                 deepseek_api_key: str = None):
        self.driver = GraphDatabase.driver(neo4j_uri, auth=(neo4j_user, neo4j_password))
        self.deepseek_api_key = deepseek_api_key or os.getenv('DEEPSEEK_API_KEY')
        self.deepseek_api_url = "https://api.deepseek.com/v1/chat/completions"

    def close(self):
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
        prompt = f"""分析以下医疗文档,提取实体和关系。

实体类型: Disease(疾病), Treatment(治疗), Examination(检查), Medication(药物), Department(科室), VitalSign(生命体征), Complication(并发症)

关系类型: REQUIRES_TREATMENT(需要治疗), REQUIRES_EXAMINATION(需要检查), USES_MEDICATION(使用药物), BELONGS_TO_DEPARTMENT(属于科室), MONITORS_SIGN(检测指标), CAUSES_COMPLICATION(引起并发症)

重要规则:
1. 返回纯JSON,不要markdown标记
2. 属性值用简单文本,避免特殊字符
3. properties可以为空对象
4. 确保JSON格式正确

输出格式:
{{
  "entities": [
    {{"id": "d1", "type": "Disease", "name": "心脏骤停", "properties": {{}}}},
    {{"id": "t1", "type": "Treatment", "name": "心肺复苏", "properties": {{}}}}
  ],
  "relationships": [
    {{"from": "d1", "to": "t1", "type": "REQUIRES_TREATMENT", "properties": {{}}}}
  ]
}}

文档:
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
                    "content": "你是JSON数据提取专家。只返回有效的JSON,不要任何其他内容。"
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "temperature": 0,  # 设置为0以获得最确定的输出
            "max_tokens": 4000
        }

        try:
            response = requests.post(self.deepseek_api_url, headers=headers, json=payload, timeout=120)
            response.raise_for_status()

            response_data = response.json()
            response_text = response_data['choices'][0]['message']['content']

            # 调试信息
            print(f"  原始响应长度: {len(response_text)} 字符")

            # 多层清理和修复
            response_text = self._clean_json_response(response_text)
            response_text = self._extract_json_from_text(response_text)

            # 尝试解析
            try:
                kg_data = json.loads(response_text)
            except json.JSONDecodeError as e:
                print(f"  第一次解析失败: {e}")

                # 保存原始错误响应
                error_file = f'error_batch_{batch_idx}_raw.txt'
                with open(error_file, 'w', encoding='utf-8') as f:
                    f.write(response_text)
                print(f"  原始响应已保存: {error_file}")

                # 尝试激进修复
                print(f"  尝试修复JSON...")
                response_text = self._fix_json_errors(response_text)

                # 保存修复后的文本
                fixed_file = f'error_batch_{batch_idx}_fixed.txt'
                with open(fixed_file, 'w', encoding='utf-8') as f:
                    f.write(response_text)
                print(f"  修复后保存: {fixed_file}")

                # 再次尝试解析
                kg_data = json.loads(response_text)

            # 验证并修复结构
            if 'entities' not in kg_data:
                print(f"  警告: 缺少entities字段,创建空列表")
                kg_data['entities'] = []

            if 'relationships' not in kg_data:
                print(f"  警告: 缺少relationships字段,创建空列表")
                kg_data['relationships'] = []

            # 清理无效数据
            kg_data['entities'] = [e for e in kg_data['entities']
                                   if 'id' in e and 'type' in e and 'name' in e]
            kg_data['relationships'] = [r for r in kg_data['relationships']
                                        if 'from' in r and 'to' in r and 'type' in r]

            return kg_data

        except json.JSONDecodeError as e:
            print(f"  JSON解析失败(无法修复): {e}")
            print(f"  错误位置: 第{e.lineno}行, 第{e.colno}列")

            # 返回空结果而不是抛出异常
            return {'entities': [], 'relationships': []}

        except Exception as e:
            print(f"  处理失败: {e}")
            import traceback
            traceback.print_exc()
            return {'entities': [], 'relationships': []}

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
        # 移除markdown代码块标记 (包括各种变体)
        text = re.sub(r'```json\s*\n?', '', text, flags=re.IGNORECASE)
        text = re.sub(r'```\s*\n?', '', text)

        # 移除BOM
        if text.startswith('\ufeff'):
            text = text[1:]

        # 去除首尾空白
        text = text.strip()

        # 如果文本以非JSON字符开始,尝试找到第一个{
        if text and text[0] not in ('{', '['):
            first_brace = text.find('{')
            if first_brace != -1:
                text = text[first_brace:]


        # 如果文本以非JSON字符结束,尝试找到最后一个}
        if text and text[-1] not in ('}', ']'):
            last_brace = text.rfind('}')
            if last_brace != -1:
                text = text[:last_brace + 1]

        return text

    def _fix_json_errors(self, text: str) -> str:
        """尝试修复常见的JSON错误"""
        import re

        # 1. 移除控制字符
        text = ''.join(char for char in text if ord(char) >= 32 or char in '\n\r\t')

        # 2. 修复单引号
        text = text.replace("'", '"')

        # 3. 修复尾随逗号
        text = re.sub(r',\s*}', '}', text)
        text = re.sub(r',\s*]', ']', text)

        # 4. 修复属性值中的未转义引号
        # 查找 "key": "value with "quote"" 这种情况
        def fix_quotes_in_values(match):
            value = match.group(1)
            # 转义内部的引号
            fixed_value = value.replace('"', '\\"')
            return f'": "{fixed_value}"'

        # 5. 修复缺少逗号的情况
        text = re.sub(r'}\s*{', '},{', text)
        text = re.sub(r']\s*{', '],{', text)
        text = re.sub(r'}\s*\[', '},[', text)

        # 6. 修复属性名没有引号的情况
        text = re.sub(r'(\w+)(\s*:\s*)', r'"\1"\2', text)

        # 7. 移除注释
        text = re.sub(r'//.*?\n', '\n', text)
        text = re.sub(r'/\*.*?\*/', '', text, flags=re.DOTALL)

        return text

    def _extract_json_from_text(self, text: str) -> str:
        """从文本中提取JSON部分"""
        # 尝试找到最外层的大括号
        stack = []
        start_idx = -1

        for i, char in enumerate(text):
            if char == '{':
                if not stack:
                    start_idx = i
                stack.append(char)
            elif char == '}':
                if stack:
                    stack.pop()
                    if not stack and start_idx != -1:
                        # 找到完整的JSON对象
                        return text[start_idx:i + 1]

        # 如果没找到,返回原文本
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


def test_deepseek_connection(api_key: str):
    """测试DeepSeek API连接和JSON输出"""
    print("=" * 50)
    print("测试DeepSeek API连接...")
    print("=" * 50)

    test_text = """
    心脏骤停是指心脏突然停止跳动。需要立即进行心肺复苏。
    主要治疗措施包括:
    1. 胸外按压
    2. 人工呼吸
    3. 使用除颤器
    需要监测心率和血压。
    """

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }

    payload = {
        "model": "deepseek-chat",
        "messages": [
            {
                "role": "system",
                "content": "你是JSON专家。只返回JSON格式数据,不要markdown代码块。"
            },
            {
                "role": "user",
                "content": f"""提取以下文本的实体和关系,返回JSON:

{{
  "entities": [
    {{"id": "d1", "type": "Disease", "name": "心脏骤停"}},
    {{"id": "t1", "type": "Treatment", "name": "心肺复苏"}}
  ],
  "relationships": [
    {{"from": "d1", "to": "t1", "type": "REQUIRES_TREATMENT"}}
  ]
}}

文本: {test_text}"""
            }
        ],
        "temperature": 0,
        "max_tokens": 500
    }

    try:
        response = requests.post(
            "https://api.deepseek.com/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=30
        )
        response.raise_for_status()

        data = response.json()
        content = data['choices'][0]['message']['content']

        print("\n原始响应:")
        print(content)
        print("\n" + "=" * 50)

        # 清理markdown代码块
        content_cleaned = re.sub(r'```json\s*', '', content)
        content_cleaned = re.sub(r'```\s*', '', content_cleaned)
        content_cleaned = content_cleaned.strip()

        if content_cleaned != content:
            print("\n清理后的JSON:")
            print(content_cleaned)
            print("\n" + "=" * 50)

        # 尝试解析
        try:
            parsed = json.loads(content_cleaned)
            print("✓ JSON解析成功!")
            print(f"  实体数: {len(parsed.get('entities', []))}")
            print(f"  关系数: {len(parsed.get('relationships', []))}")
            return True
        except json.JSONDecodeError as e:
            print(f"✗ JSON解析失败: {e}")
            print(f"  位置: 第{e.lineno}行, 第{e.colno}列")

            # 显示出错位置附近的内容
            lines = content_cleaned.split('\n')
            if e.lineno <= len(lines):
                print(f"  出错行内容: {lines[e.lineno - 1]}")

            return False

    except Exception as e:
        print(f"✗ API调用失败: {e}")
        return False


def main():
    """主函数"""

    # Neo4j连接配置
    NEO4J_URI = "bolt://localhost:7687"
    NEO4J_USER = "neo4j"
    NEO4J_PASSWORD = "aqzdwsfneo"  # 请修改为你的密码

    # DeepSeek API密钥
    DEEPSEEK_API_KEY = os.getenv('DEEPSEEK_API_KEY') or "sk-8cbf10f456ae40aba1be330eaa3c2397"

    # 分批处理配置
    CHUNK_SIZE = 1500  # 减小批次大小到2000字符

    # 先测试API连接
    print("步骤1: 测试DeepSeek API")
    if not test_deepseek_connection(DEEPSEEK_API_KEY):
        print("\n请检查:")
        print("1. DEEPSEEK_API_KEY是否正确")
        print("2. 网络连接是否正常")
        print("3. API配额是否充足")
        return

    print("\n步骤2: 读取文档")
    # 读取文档
    base_dir = os.path.dirname(os.path.abspath(__file__))
    text_dir = os.path.join(base_dir, "words/需要紧急救治的急危重伤病标准.docx")

    # 读取.docx文件
    document_text = readDocx(text_dir)

    print("\n步骤3: 构建知识图谱")
    # 创建知识图谱构建器
    builder = MedicalKGBuilder(NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD, DEEPSEEK_API_KEY)

    try:
        # 构建知识图谱(分批处理)
        kg_data = builder.build_knowledge_graph(document_text, chunk_size=CHUNK_SIZE)

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
        print("\n示例查询 - 查找所有疾病(前10个):")
        diseases = builder.query_graph("MATCH (d:Disease) RETURN d.name as name LIMIT 10")
        for disease in diseases:
            print(f"  - {disease['name']}")

        print("\n示例查询 - 查找心脏骤停的治疗措施:")
        treatments = builder.query_graph("""
            MATCH (d:Disease)-[:REQUIRES_TREATMENT]->(t:Treatment)
            WHERE d.name CONTAINS '心脏骤停'
            RETURN t.name as treatment
        """)
        if treatments:
            for treatment in treatments:
                print(f"  - {treatment['treatment']}")
        else:
            print("  未找到相关数据")

        print("\n示例查询 - 统计各类型实体数量:")
        type_stats = builder.query_graph("""
            MATCH (n)
            RETURN labels(n)[0] as type, count(n) as count
            ORDER BY count DESC
        """)
        for stat in type_stats:
            print(f"  {stat['type']}: {stat['count']}")

    except Exception as e:
        print(f"\n发生错误: {e}")
        import traceback
        traceback.print_exc()
    finally:
        builder.close()
        print("\n数据库连接已关闭")


if __name__ == "__main__":
    main()