#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
代码质量评估脚本
自动化评估Git仓库中目标人群在指定时间段内的代码提交质量和数量
"""
import os
import re
import ast
import git
import pandas as pd
from datetime import datetime, timedelta
from typing import List, Dict, Tuple, Any
from collections import defaultdict
from tabulate import tabulate
import warnings
warnings.filterwarnings('ignore')

# 配置参数
LOCAL_REPO_PATH = "/Users/zhangbo/Desktop/maxkb"
START_DATE = "2025-02-27"
END_DATE = "2025-7-18"
AUTHORS = [
    "zhangbo0037", 
    "陈项世隆",
    "JohanLi233",
    "张点点"
]

class GitRepository:
    """Git仓库操作类"""
    
    def __init__(self, local_path: str):
        """
        初始化Git仓库连接
        
        Args:
            local_path: 本地仓库路径
        """
        self.local_path = local_path
        self.repo = None
    
        
    def initialize_repo(self) -> bool:
        """
        初始化本地仓库
        
        Returns:
            bool: 操作是否成功
        """
        try:
            print(f"📁 使用本地仓库: {self.local_path}")
            
            if not os.path.exists(self.local_path):
                print(f"✗ 本地仓库路径不存在: {self.local_path}")
                return False
            
            if not os.path.exists(os.path.join(self.local_path, '.git')):
                print(f"✗ 指定路径不是Git仓库: {self.local_path}")
                return False
            
            self.repo = git.Repo(self.local_path)
            print(f"✓ 成功加载本地仓库: {self.local_path}")
            return True
            
        except Exception as e:
            print(f"✗ 仓库初始化失败: {str(e)}")
            return False
    
    def get_current_branch(self) -> str:
        """
        获取当前分支名称
        
        Returns:
            str: 当前分支名称
        """
        if not self.repo:
            return "unknown"
        
        try:
            return self.repo.active_branch.name
        except:
            # 如果无法获取active_branch（如detached HEAD状态），返回HEAD的短hash
            try:
                return self.repo.head.commit.hexsha[:7]
            except:
                return "unknown"
    
    def get_commits_by_author_and_time(self, authors: List[str], start_date: str, end_date: str) -> Dict[str, List[git.Commit]]:
        """
        获取指定作者在指定时间段内的提交记录
        
        Args:
            authors: 作者列表
            start_date: 开始日期 (YYYY-MM-DD)
            end_date: 结束日期 (YYYY-MM-DD)
            
        Returns:
            Dict[str, List[git.Commit]]: 按作者分组的提交记录
        """
        if not self.repo:
            return {}
        
        # 转换日期格式
        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        end_dt = datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)
        
        commits_by_author = defaultdict(list)
        
        for commit in self.repo.iter_commits(since=start_dt, until=end_dt):
            author_name = commit.author.name
            # 检查是否为目标作者
            for target_author in authors:
                if target_author in author_name or author_name in target_author:
                    commits_by_author[author_name].append(commit)
                    break
        
        return dict(commits_by_author)
    
    def get_diff_stats(self, commit: git.Commit) -> Tuple[int, int, int]:
        """
        获取提交的代码变更统计
        
        Args:
            commit: Git提交对象
            
        Returns:
            Tuple[int, int, int]: (新增行数, 删除行数, 总变更行数)
        """
        try:
            stats = commit.stats
            return stats.total['insertions'], stats.total['deletions'], stats.total['lines']
        except:
            return 0, 0, 0
    
    def get_commit_diff_content(self, commit: git.Commit) -> List[str]:
        """
        获取提交的具体代码变更内容
        
        Args:
            commit: Git提交对象
            
        Returns:
            List[str]: 代码变更内容行列表
        """
        try:
            # 获取与父提交的差异
            if commit.parents:
                diff = commit.parents[0].diff(commit, create_patch=True)
            else:
                # 初始提交
                diff = commit.diff(git.NULL_TREE, create_patch=True)
            
            diff_lines = []
            for item in diff:
                if item.diff:
                    diff_lines.extend(item.diff.decode('utf-8', errors='ignore').split('\n'))
            
            return diff_lines
        except:
            return []

class CodeQualityAnalyzer:
    """代码质量分析器"""
    
    def __init__(self):
        """初始化代码质量分析器"""
        self.quality_patterns = {
            '死代码': [
                r'^\s*#.*TODO.*$',  # TODO注释
                r'^\s*#.*FIXME.*$',  # FIXME注释
                r'^\s*#.*HACK.*$',   # HACK注释
                r'^\s*def\s+\w+.*:\s*pass\s*$',  # 空函数
                r'^\s*class\s+\w+.*:\s*pass\s*$',  # 空类
            ],
            '重复代码': [
                r'(.{20,})\n(?:.*\n){0,5}\1',  # 重复的代码块
            ],
            '安全漏洞': [
                r'eval\s*\(',  # eval函数使用
                r'exec\s*\(',  # exec函数使用
                r'subprocess\..*shell=True',  # shell注入风险
                r'os\.system\s*\(',  # 系统命令执行
                r'pickle\.loads?\s*\(',  # pickle反序列化
                r'yaml\.load\s*\(',  # yaml不安全加载
            ],
            '性能瓶颈': [
                r'for\s+\w+\s+in\s+range\s*\(\s*len\s*\(',  # 低效循环
                r'\+\s*=.*\+.*\+',  # 字符串拼接
                r'\.append\s*\(.*\)\s*\n.*\.append\s*\(',  # 多次append
            ],
            '风格一致性': [
                r'^\s{1,3}\S',  # 不规范缩进
                r'=\s{2,}',  # 多余空格
                r'\s+$',  # 行尾空格
                r'^[a-z]+[A-Z]',  # 驼峰命名(Python推荐下划线)
            ],
            '注释缺失': [
                r'^\s*def\s+[^_].*:(?!\s*""")',  # 函数缺少文档字符串
                r'^\s*class\s+\w+.*:(?!\s*""")',  # 类缺少文档字符串
            ]
        }
    
    def analyze_code_content(self, code_lines: List[str]) -> Dict[str, int]:
        """
        分析代码内容，检测各类质量问题
        
        Args:
            code_lines: 代码行列表
            
        Returns:
            Dict[str, int]: 各类问题的数量统计
        """
        issues = defaultdict(int)
        code_content = '\n'.join(code_lines)
        
        for issue_type, patterns in self.quality_patterns.items():
            for pattern in patterns:
                matches = re.findall(pattern, code_content, re.MULTILINE | re.IGNORECASE)
                issues[issue_type] += len(matches)
        
        return dict(issues)
    
    def analyze_python_syntax(self, code_content: str) -> Dict[str, int]:
        """
        分析Python代码的语法质量
        
        Args:
            code_content: Python代码内容
            
        Returns:
            Dict[str, int]: 语法问题统计
        """
        issues = defaultdict(int)
        
        try:
            # 尝试解析AST
            tree = ast.parse(code_content)
            
            # 检查复杂度
            for node in ast.walk(tree):
                # 函数复杂度检查
                if isinstance(node, ast.FunctionDef):
                    complexity = self._calculate_complexity(node)
                    if complexity > 10:  # 复杂度阈值
                        issues['高复杂度函数'] += 1
                
                # 嵌套深度检查
                if isinstance(node, (ast.For, ast.While, ast.If)):
                    depth = self._calculate_nesting_depth(node)
                    if depth > 3:  # 嵌套深度阈值
                        issues['过深嵌套'] += 1
        
        except SyntaxError:
            issues['语法错误'] += 1
        except:
            pass
        
        return dict(issues)
    
    def _calculate_complexity(self, node: ast.AST) -> int:
        """计算函数复杂度"""
        complexity = 1
        for child in ast.walk(node):
            if isinstance(child, (ast.If, ast.For, ast.While, ast.Try, ast.ExceptHandler)):
                complexity += 1
        return complexity
    
    def _calculate_nesting_depth(self, node: ast.AST, depth: int = 0) -> int:
        """计算嵌套深度"""
        max_depth = depth
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.For, ast.While, ast.If, ast.Try)):
                child_depth = self._calculate_nesting_depth(child, depth + 1)
                max_depth = max(max_depth, child_depth)
        return max_depth

class CodeQuantityAnalyzer:
    """代码数量分析器"""
    
    def __init__(self):
        """初始化代码数量分析器"""
        pass
    
    def analyze_commit_quantity(self, commits: List[git.Commit]) -> Dict[str, int]:
        """
        分析提交的代码数量指标
        
        Args:
            commits: 提交列表
            
        Returns:
            Dict[str, int]: 数量指标统计
        """
        total_insertions = 0
        total_deletions = 0
        total_commits = len(commits)
        total_files_changed = 0
        
        for commit in commits:
            try:
                stats = commit.stats
                total_insertions += stats.total['insertions']
                total_deletions += stats.total['deletions']
                total_files_changed += stats.total['files']
            except:
                continue
        
        return {
            '提交次数': total_commits,
            '新增代码行数': total_insertions,
            '删除代码行数': total_deletions,
            '净增代码行数': total_insertions - total_deletions,
            '修改文件数': total_files_changed,
            '总变更行数': total_insertions + total_deletions
        }

class MetricsCalculator:
    """指标计算器"""
    
    def __init__(self):
        """初始化指标计算器"""
        pass
    
    def calculate_quality_metrics(self, total_issues: int, total_lines: int) -> Dict[str, float]:
        """
        计算代码质量相关指标
        
        Args:
            total_issues: 总问题数
            total_lines: 总代码行数
            
        Returns:
            Dict[str, float]: 质量指标
        """
        if total_lines == 0:
            return {
                '千行代码问题数': 0.0,
                '千行代码问题率': 0.0,
                '质量分数': 100.0
            }
        
        # 千行代码问题数
        issues_per_kloc = (total_issues / total_lines) * 1000
        
        # 千行代码问题率 (‰)
        issue_rate_per_kloc = (total_issues / total_lines) * 1000
        
        # 质量分数计算 (100分制，问题越少分数越高)
        quality_score = max(0, 100 - (issues_per_kloc * 2))  # 每千行1个问题扣2分
        
        return {
            '千行代码问题数': round(issues_per_kloc, 2),
            '千行代码问题率': round(issue_rate_per_kloc, 2),
            '质量分数': round(quality_score, 2)
        }
    
    def calculate_quantity_score(self, total_lines: int, avg_lines: int) -> float:
        """
        计算代码数量分数
        
        Args:
            total_lines: 个人总代码行数
            avg_lines: 平均代码行数
            
        Returns:
            float: 数量分数
        """
        if avg_lines == 0:
            return 50.0  # 默认中等分数
        
        # 相对于平均值的百分比
        ratio = total_lines / avg_lines
        
        # 数量分数计算 (100分制)
        if ratio >= 2.0:
            score = 100
        elif ratio >= 1.5:
            score = 90
        elif ratio >= 1.0:
            score = 80
        elif ratio >= 0.8:
            score = 70
        elif ratio >= 0.6:
            score = 60
        elif ratio >= 0.4:
            score = 50
        elif ratio >= 0.2:
            score = 40
        else:
            score = 30
        
        return float(score)
    
    def calculate_final_score(self, quality_score: float, quantity_score: float) -> float:
        """
        计算最终综合分数
        
        Args:
            quality_score: 质量分数
            quantity_score: 数量分数
            
        Returns:
            float: 综合分数
        """
        # 质量占80%，数量占20%
        final_score = quality_score * 0.8 + quantity_score * 0.2
        return round(final_score, 2)

class ReportGenerator:
    """报告生成器"""
    
    def __init__(self):
        """初始化报告生成器"""
        pass
    
    def generate_report_table(self, results: List[Dict[str, Any]], time_period: str) -> str:
        """
        生成评估报告表格
        
        Args:
            results: 评估结果列表
            time_period: 时间段描述
            
        Returns:
            str: 格式化的表格字符串
        """
        if not results:
            return "没有找到符合条件的数据"
        
        # 准备表格数据
        table_data = []
        headers = [
            "贡献者", "时间段", "提交次数", "代码行数", "总问题数",
            "千行代码问题数", "千行代码问题率", "质量分数", "数量分数", "综合分数"
        ]
        
        for result in results:
            row = [
                result.get('贡献者', ''),
                time_period,
                result.get('提交次数', 0),
                result.get('总变更行数', 0),
                result.get('总问题数', 0),
                result.get('千行代码问题数', 0.0),
                f"{result.get('千行代码问题率', 0.0)}‰",
                result.get('质量分数', 0.0),
                result.get('数量分数', 0.0),
                result.get('综合分数', 0.0)
            ]
            table_data.append(row)
        
        # 生成表格
        table_str = tabulate(table_data, headers=headers, tablefmt='grid', floatfmt='.2f')
        
        return table_str

class CodeQualityScanner:
    """代码质量扫描主程序"""
    
    def __init__(self):
        """初始化扫描器"""
        self.git_repo = None
        self.quality_analyzer = CodeQualityAnalyzer()
        self.quantity_analyzer = CodeQuantityAnalyzer()
        self.metrics_calculator = MetricsCalculator()
        self.report_generator = ReportGenerator()
    
    def run_analysis(self, local_path: str, authors: List[str], start_date: str, end_date: str) -> str:
        """
        运行完整的代码质量分析
        
        Args:
            local_path: 本地仓库路径
            authors: 目标作者列表
            start_date: 开始日期
            end_date: 结束日期
            
        Returns:
            str: 分析报告
        """
        # 1. 初始化Git仓库
        self.git_repo = GitRepository(local_path)
        if not self.git_repo.initialize_repo():
            return "❌ 仓库初始化失败，请检查本地路径"
        
        # 获取当前分支信息
        current_branch = self.git_repo.get_current_branch()
        print(f"🌿 当前分支: {current_branch}")
        
        print("-" * 80)
        print("🔍 代码质量评估开始")
        print("-" * 80)

        # 2. 获取目标作者的提交记录
        print(f"📊 分析时间段: {start_date} 至 {end_date}")

        print(f"\n👥 目标作者: {', '.join(authors)}")
        
        commits_by_author = self.git_repo.get_commits_by_author_and_time(authors, start_date, end_date)
        
        if not commits_by_author:
            return "❌ 未找到指定时间段内目标作者的提交记录"
        
        # 3. 分析每个作者的代码质量和数量
        results = []
        all_total_lines = []
        
        for author, commits in commits_by_author.items():
            print(f"\n🔍 正在分析 {author} 的代码...")
            result = self._analyze_author_code(author, commits)
            results.append(result)
            all_total_lines.append(result.get('总变更行数', 0))
        
        # 4. 计算平均代码行数用于数量分数计算
        avg_lines = sum(all_total_lines) / len(all_total_lines) if all_total_lines else 0
        
        # 5. 更新数量分数
        for result in results:
            total_lines = result.get('总变更行数', 0)
            quantity_score = self.metrics_calculator.calculate_quantity_score(total_lines, avg_lines)
            result['数量分数'] = quantity_score
            
            # 重新计算综合分数
            quality_score = result.get('质量分数', 0)
            final_score = self.metrics_calculator.calculate_final_score(quality_score, quantity_score)
            result['综合分数'] = final_score
        
        # 6. 生成报告
        time_period = f"{start_date} 至 {end_date}"
        report = self.report_generator.generate_report_table(results, time_period)
        
        print("\n" + "-" * 80)
        print("📋 代码质量评估报告")
        print("-" * 80)
        print(report)
        
        # 7. 保存报告到Excel文件
        self._save_report_to_excel(results, time_period)
        
        return report
    
    def _analyze_author_code(self, author: str, commits: List[git.Commit]) -> Dict[str, Any]:
        """
        分析单个作者的代码质量和数量
        
        Args:
            author: 作者名称
            commits: 作者的提交列表
            
        Returns:
            Dict[str, Any]: 作者的分析结果
        """
        # 代码数量分析
        quantity_metrics = self.quantity_analyzer.analyze_commit_quantity(commits)
        
        # 收集所有代码变更内容进行质量分析
        all_code_lines = []
        total_issues = 0
        
        for commit in commits:
            diff_lines = self.git_repo.get_commit_diff_content(commit)
            # 过滤出新增的代码行（以+开头的行）
            new_lines = [line[1:] for line in diff_lines if line.startswith('+') and not line.startswith('+++')]
            all_code_lines.extend(new_lines)
        
        # 代码质量分析
        if all_code_lines:
            quality_issues = self.quality_analyzer.analyze_code_content(all_code_lines)
            total_issues = sum(quality_issues.values())
            
            # 如果有Python代码，进行语法分析
            python_code = '\n'.join([line for line in all_code_lines if any(keyword in line for keyword in ['def ', 'class ', 'import '])])
            if python_code:
                syntax_issues = self.quality_analyzer.analyze_python_syntax(python_code)
                total_issues += sum(syntax_issues.values())
        
        # 计算质量指标
        total_lines = quantity_metrics.get('总变更行数', 0)
        quality_metrics = self.metrics_calculator.calculate_quality_metrics(total_issues, total_lines)
        
        # 整合结果
        result = {
            '贡献者': author,
            '提交次数': quantity_metrics.get('提交次数', 0),
            '总变更行数': total_lines,
            '总问题数': total_issues,
            '千行代码问题数': quality_metrics.get('千行代码问题数', 0.0),
            '千行代码问题率': quality_metrics.get('千行代码问题率', 0.0),
            '质量分数': quality_metrics.get('质量分数', 0.0),
            '数量分数': 0.0,  # 后续计算
            '综合分数': 0.0   # 后续计算
        }
        
        return result
    
    def _save_report_to_excel(self, results: List[Dict[str, Any]], time_period: str):
        """
        保存报告到Excel文件
        
        Args:
            results: 评估结果列表
            time_period: 时间段描述
        """
        try:
            # 生成Excel文件名（格式：result-年月日时分秒.xlsx）
            timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
            excel_filename = f"result-{timestamp}.xlsx"
            
            # 准备DataFrame数据
            df_data = []
            for result in results:
                row = {
                    '贡献者': result.get('贡献者', ''),
                    '时间段': time_period,
                    '提交次数': result.get('提交次数', 0),
                    '代码行数': result.get('总变更行数', 0),
                    '总问题数': result.get('总问题数', 0),
                    '千行代码问题数': result.get('千行代码问题数', 0.0),
                    '千行代码问题率': result.get('千行代码问题率', 0.0),
                    '质量分数': result.get('质量分数', 0.0),
                    '数量分数': result.get('数量分数', 0.0),
                    '综合分数': result.get('综合分数', 0.0)
                }
                df_data.append(row)
            
            # 创建DataFrame
            df = pd.DataFrame(df_data)
            
            # 保存到Excel文件
            with pd.ExcelWriter(excel_filename, engine='openpyxl') as writer:
                df.to_excel(writer, sheet_name='代码质量评估报告', index=False)
                
                # 获取工作表对象进行格式化
                worksheet = writer.sheets['代码质量评估报告']
                
                # 调整列宽
                for column in worksheet.columns:
                    max_length = 0
                    column_letter = column[0].column_letter
                    for cell in column:
                        try:
                            if len(str(cell.value)) > max_length:
                                max_length = len(str(cell.value))
                        except:
                            pass
                    adjusted_width = min(max_length + 2, 20)
                    worksheet.column_dimensions[column_letter].width = adjusted_width
            
            print(f"\n📊 报告已保存到Excel文件: {excel_filename}")
            
        except Exception as e:
            print(f"\n⚠️  保存Excel文件失败: {str(e)}")

def main():
    """主程序入口"""
    print("-" * 50)
    print("🚀 代码质量评估工具")
    print("-" * 50)
    
    # 使用宏定义的时间段
    print(f"📅 评估时间段: {START_DATE} 至 {END_DATE}")
    print("💡 如需修改时间段，请在代码顶部修改 START_DATE 和 END_DATE 宏定义")
    
    # 创建扫描器并运行分析
    scanner = CodeQualityScanner()
    
    try:
        scanner.run_analysis(
            local_path=LOCAL_REPO_PATH,
            authors=AUTHORS,
            start_date=START_DATE,
            end_date=END_DATE
        )
        
        print(f"\n✅ 评估完成！")
        
    except KeyboardInterrupt:
        print("\n⏹️  用户中断了评估过程")
    except Exception as e:
        print(f"\n❌ 评估过程中发生错误: {str(e)}")


if __name__ == "__main__":
    main()