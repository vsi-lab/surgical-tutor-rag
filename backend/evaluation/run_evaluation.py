"""
Comprehensive Evaluation Runner
Main script to run all experiments and generate publication-ready results

NOTE: This is a template. You need to integrate with your actual RAG system.
"""

import asyncio
import json
import os
import sys
from typing import Dict, List, Optional
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
env_path = Path(__file__).parent.parent / '.env'
load_dotenv(env_path)

# Add parent directory to import backend modules
sys.path.insert(0, str(Path(__file__).parent.parent))

# Import actual RAG components
try:
    from modules.embedder.embedder import BioClinicalEmbedder
    from modules.retriever.faiss_manager import FaissManager
    from modules.generator.generator import Generator
    RAG_IMPORTS_AVAILABLE = True
except ImportError as e:
    RAG_IMPORTS_AVAILABLE = False
    print(f"[WARNING] RAG imports unavailable: {e}")

# Try importing graph components
try:
    from modules.graph.neo4j_manager import Neo4jManager
    from modules.graph.entity_extractor import MedicalEntityExtractor
    from modules.graph.graph_retriever import GraphEnhancedRetriever
    GRAPH_AVAILABLE = True
except ImportError:
    GRAPH_AVAILABLE = False

# Try importing verification components
try:
    from modules.verification import VerificationPipeline
    VERIFICATION_AVAILABLE = True
except ImportError:
    VERIFICATION_AVAILABLE = False
    print("[WARNING] Verification pipeline unavailable")

try:
    import pandas as pd
    import matplotlib.pyplot as plt
    import seaborn as sns
    HAS_VISUALIZATION = True
except ImportError:
    HAS_VISUALIZATION = False
    print("Warning: pandas/matplotlib not installed. Visualizations will be skipped.")

from metrics.retrieval_metrics import evaluate_retrieval, RetrievalMetrics, source_chunk_id
from revision.data_audit import build_corpus_manifest, resolve_legacy_qrel
from metrics.qa_metrics import evaluate_qa, QAMetrics
from metrics.hallucination_metrics import evaluate_hallucination
from ablation_study import AblationStudy
from test_data.dataset_generator import QADatasetGenerator


class ComprehensiveEvaluator:
    """Run complete evaluation suite for publication"""
    
    def __init__(
        self,
        config_file: str = "config.json",
        output_dir: str = "results"
    ):
        """
        Initialize comprehensive evaluator
        
        Args:
            config_file: Path to configuration file
            output_dir: Directory for results
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Load configuration
        if Path(config_file).exists():
            with open(config_file, 'r') as f:
                self.config = json.load(f)
        else:
            print(f"Warning: Config file {config_file} not found. Using defaults.")
            self.config = self._get_default_config()
        
        self.results = {
            'experiment_id': datetime.now().strftime('%Y%m%d_%H%M%S'),
            'config': self.config,
            'dataset_stats': {},
            'retrieval_results': {},
            'qa_results': {},
            'hallucination_results': {},
            'verification_results': {},  # NEW: Verification metrics
            'ablation_results': {},
            'baseline_comparison': {}
        }
        
        # Initialize RAG components
        self.embedder = None
        self.faiss = None
        self.generator = None
        self.graph_retriever = None
        self.verification_pipeline = None  # NEW: Verification pipeline
        if RAG_IMPORTS_AVAILABLE:
            self._init_rag_components()
    
    def _get_default_config(self) -> Dict:
        """Get default configuration"""
        import os
        return {
            'dataset': {
                'test_file': 'test_data/miccai_test_set_50plus.json',
                'questions_per_chunk': 3,
                'test_ratio': 0.2
            },
            'evaluation': {
                'k_values': [1, 3, 5, 10]
            },
            'api_key': os.getenv('OPENROUTER_API_KEY', '')
        }
    
    def _init_rag_components(self):
        """Initialize the actual RAG system components"""
        try:
            # Initialize embedder
            model_name = self.config.get('bioclinicalbert_model', 'emilyalsentzer/Bio_ClinicalBERT')
            self.embedder = BioClinicalEmbedder(model_name)
            print(f"Initialized BioClinicalBERT embedder (dim={self.embedder.dim()})")
            
            # Initialize FAISS
            faiss_path = self.config.get('faiss_index_path', '../faiss_index.index')
            self.faiss = FaissManager(dim=self.embedder.dim(), index_path=faiss_path)
            try:
                self.faiss.load(faiss_path)
                print(f"Loaded FAISS index: {self.faiss.index.ntotal} vectors")
            except:
                print("No existing FAISS index found or empty index")
            
            # Initialize generator
            api_key = self.config.get('api_key') or os.getenv('OPENAI_API_KEY') or os.getenv('OPENROUTER_API_KEY')
            self.generator = Generator(openai_api_key=api_key)
            print("Initialized GPT-4o generator")
            
            # Try to initialize graph components if available
            if GRAPH_AVAILABLE:
                try:
                    neo4j_config = self.config.get('neo4j', {})
                    neo4j = Neo4jManager(
                        neo4j_config.get('uri', 'bolt://localhost:7687'),
                        neo4j_config.get('user', 'neo4j'),
                        neo4j_config.get('password', 'password')
                    )
                    scispacy_model = self.config.get('scispacy_model', 'en_core_sci_md')
                    entity_extractor = MedicalEntityExtractor(scispacy_model)
                    self.graph_retriever = GraphEnhancedRetriever(
                        self.faiss,
                        neo4j,
                        entity_extractor,
                        self.embedder,
                        vector_weight=0.6,
                        graph_weight=0.4
                    )
                    print("Initialized graph-enhanced retrieval")
                    
                    # Initialize verification pipeline with graph
                    if VERIFICATION_AVAILABLE:
                        try:
                            self.verification_pipeline = VerificationPipeline(
                                neo4j_manager=neo4j,
                                api_key=api_key,
                                abstention_threshold=self.config.get('abstention_threshold', 0.5),
                                enable_abstention=self.config.get('enable_abstention', True)
                            )
                            print("Initialized verification pipeline with hallucination taxonomy and abstention")
                        except Exception as e:
                            print(f"Verification pipeline unavailable: {e}")
                except Exception as e:
                    print(f"Graph features unavailable: {e}")
                    
        except Exception as e:
            print(f"Error initializing RAG components: {e}")
            print("Continuing with placeholder mode")
    
    async def run_full_evaluation(self):
        """Run complete evaluation pipeline"""
        print("="*80)
        print("COMPREHENSIVE RAG SYSTEM EVALUATION")
        print("="*80)
        
        # 1. Load or generate test dataset
        print("\n[1/7] Loading test dataset...")
        test_data = await self._load_test_dataset()
        
        # 2. Evaluate retrieval performance
        print("\n[2/7] Evaluating retrieval performance...")
        self.results['retrieval_results'] = self._evaluate_retrieval(test_data)
        
        # 3. Evaluate QA performance
        print("\n[3/7] Evaluating QA performance...")
        self.results['qa_results'] = self._evaluate_qa(test_data)
        
        # 4. Evaluate hallucination/faithfulness
        print("\n[4/7] Evaluating hallucination rates...")
        self.results['hallucination_results'] = self._evaluate_hallucination(test_data)
        
        # 5. Evaluate verification pipeline (NEW)
        print("\n[5/7] Evaluating verification pipeline...")
        self.results['verification_results'] = self._evaluate_verification(test_data)
        
        # 6. Run ablation study
        print("\n[6/7] Running ablation study...")
        self.results['ablation_results'] = self._run_ablation_study(test_data)
        
        # 7. Compare with baselines
        print("\n[7/7] Comparing with baseline systems...")
        self.results['baseline_comparison'] = await self._compare_baselines(test_data)
        
        # Generate report
        print("\n" + "="*80)
        print("GENERATING RESULTS")
        print("="*80)
        self._generate_report()
        self._generate_visualizations()
        self._export_latex_tables()
        
        print(f"\nEvaluation complete! Results saved to: {self.output_dir}")
    
    async def _load_test_dataset(self) -> Dict:
        """Load or generate test dataset"""
        dataset_path = Path(self.config['dataset']['test_file'])
        
        if dataset_path.exists():
            print(f"Loading existing test dataset: {dataset_path}")
            with open(dataset_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                dataset = data.get('qa_pairs', [])
        else:
            print("Test dataset not found. Generating new dataset...")
            
            # Load documents
            documents = self._load_documents()
            
            # Generate QA pairs
            generator = QADatasetGenerator(
                api_key=self.config['api_key'],
                output_dir=str(self.output_dir / "test_data")
            )
            
            qa_pairs = await generator.generate_dataset_from_documents(
                documents,
                questions_per_chunk=self.config['dataset']['questions_per_chunk']
            )
            
            # Split dataset
            train_set, test_set = generator.create_train_test_split(
                qa_pairs,
                test_ratio=self.config['dataset']['test_ratio']
            )
            
            generator.save_dataset(test_set, 'test_qa_pairs.json')
            dataset = test_set
        
        # Calculate dataset statistics
        if len(dataset) > 0:
            self.results['dataset_stats'] = {
                'num_examples': len(dataset),
                'avg_question_length': sum(len(qa['question']) for qa in dataset) / len(dataset),
                'avg_answer_length': sum(len(qa['answer']) for qa in dataset) / len(dataset),
                'num_unique_chunks': len(set(qa['chunk_id'] for qa in dataset))
            }
        else:
            self.results['dataset_stats'] = {'num_examples': 0}
            print("Warning: Empty dataset generated")
        
        print(f"Dataset loaded: {len(dataset)} examples")
        return dataset
    
    def _load_documents(self) -> List[Dict]:
        """Load document corpus"""
        # Placeholder - load from your actual document storage
        return []
    
    def _evaluate_retrieval(self, test_data: List[Dict]) -> Dict:
        """Evaluate resolved legacy qrels with global source/chunk/text identifiers.

        Address resolution does not establish independent relevance. This legacy
        runner must not be used to describe retrieval-filtered questions as a new
        held-out benchmark. Audit and explicitly resolve/exclude unjudged queries
        before calling it; invalid labels and retrieval failures are not zero scores.
        """
        if self.faiss is None or self.embedder is None:
            raise RuntimeError("Retrieval evaluation requires an initialized index and embedder")
        _, lookup, _ = build_corpus_manifest(self.faiss.id_to_meta)
        queries = []
        for position, qa in enumerate(test_data, 1):
            resolution = resolve_legacy_qrel(qa, lookup)
            if not resolution['doc_ids']:
                raise ValueError(
                    f"Query {position} has {resolution['status']}; run revision/data_audit.py "
                    "and resolve or explicitly exclude missing judgments before evaluation"
                )
            queries.append({'query': qa['question'], 'relevant_doc_ids': resolution['doc_ids']})
        requested_depth = max([10] + self.config['evaluation']['k_values'])

        def retrieve_function(query):
            if self.graph_retriever:
                contexts = self.graph_retriever.retrieve(query, top_k=requested_depth, use_graph=True)
            else:
                query_emb = self.embedder.embed_texts([query])[0]
                contexts = self.faiss.query(query_emb, top_k=requested_depth)
            chunk_ids = []
            for ctx in contexts:
                meta = ctx.get('metadata', {})
                local = meta.get('chunk_index')
                if local is None:
                    local = meta.get('chunk_id')
                doc_id = source_chunk_id(meta.get('source'), local, meta.get('text'))
                if doc_id not in lookup['by_id']:
                    raise ValueError("Retrieved evidence is absent from the frozen corpus manifest")
                chunk_ids.append(doc_id)
            return chunk_ids
        
        # Evaluate
        results = evaluate_retrieval(
            queries,
            retrieve_function,
            k_values=self.config['evaluation']['k_values']
        )
        
        return results
    
    def _evaluate_qa(self, test_data: List[Dict]) -> Dict:
        """Evaluate QA metrics"""
        # Generate predictions from your system
        predictions = []
        for qa in test_data:
            # TODO: Generate prediction using your RAG system
            prediction = self._generate_answer(qa['question'])
            
            predictions.append({
                'prediction': prediction,
                'reference': qa['answer']
            })
        
        # Evaluate
        results = evaluate_qa(predictions)
        
        return results
    
    def _evaluate_hallucination(self, test_data: List[Dict]) -> Dict:
        """Evaluate hallucination rates"""
        predictions = []
        for qa in test_data:
            # TODO: Generate answer with retrieved context
            answer, context_chunks = self._generate_answer_with_context(qa['question'])
            
            predictions.append({
                'answer': answer,
                'context_chunks': context_chunks
            })
        
        # Evaluate
        results = evaluate_hallucination(predictions)
        
        return results
    
    def _evaluate_verification(self, test_data: List[Dict]) -> Dict:
        """
        Evaluate verification pipeline:
        - Abstention rate
        - Hallucination classification distribution
        - Safety scores
        - Uncertainty metrics
        """
        if not self.verification_pipeline:
            print("[WARNING] Verification pipeline not initialized. Skipping verification evaluation.")
            return {
                'abstention_rate': 0.0,
                'hallucination_distribution': {},
                'avg_safety_score': 0.0,
                'avg_uncertainty': 0.0,
                'status': 'skipped'
            }
        
        verification_reports = []
        abstention_count = 0
        hallucination_counts = {}
        severity_counts = {'critical': 0, 'high': 0, 'medium': 0, 'low': 0}
        safety_scores = []
        uncertainties = []
        
        print(f"Running verification on {len(test_data)} test examples...")
        
        for i, qa in enumerate(test_data):
            try:
                # Generate answer
                answer, context_chunks = self._generate_answer_with_context(qa['question'])
                
                # Run verification
                report = self.verification_pipeline.verify_answer(qa['question'], answer)
                verification_reports.append(report)
                
                # Count abstentions
                if report.get('abstention_decision', {}).get('should_abstain', False):
                    abstention_count += 1
                
                # Collect hallucination statistics
                hall_analysis = report.get('hallucination_analysis', {})
                for hallucination in hall_analysis.get('hallucinations', []):
                    h_type = hallucination.get('type', 'unknown')
                    hallucination_counts[h_type] = hallucination_counts.get(h_type, 0) + 1
                    
                    severity = hallucination.get('severity', 'unknown')
                    if severity in severity_counts:
                        severity_counts[severity] += 1
                
                # Collect safety scores
                safety_score = hall_analysis.get('safety_score', 1.0)
                safety_scores.append(safety_score)
                
                # Collect uncertainty
                uncertainty = report.get('uncertainty_analysis', {}).get('overall_uncertainty', 0.0)
                uncertainties.append(uncertainty)
                
                if (i + 1) % 5 == 0:
                    print(f"  Processed {i + 1}/{len(test_data)} examples...")
                    
            except Exception as e:
                print(f"  Error verifying question {i+1}: {e}")
                continue
        
        # Compile results
        abstention_rate = abstention_count / len(test_data) if test_data else 0.0
        avg_safety_score = sum(safety_scores) / len(safety_scores) if safety_scores else 0.0
        avg_uncertainty = sum(uncertainties) / len(uncertainties) if uncertainties else 0.0
        
        results = {
            'abstention_rate': abstention_rate,
            'abstention_count': abstention_count,
            'total_examples': len(test_data),
            'hallucination_distribution': hallucination_counts,
            'severity_distribution': severity_counts,
            'avg_safety_score': avg_safety_score,
            'avg_uncertainty': avg_uncertainty,
            'avg_certainty': 1.0 - avg_uncertainty,
            'verification_reports': verification_reports[:5],  # Save first 5 for inspection
            'status': 'completed'
        }
        
        print(f"\n✅ Verification evaluation complete:")
        print(f"   Abstention rate: {abstention_rate*100:.1f}%")
        print(f"   Avg safety score: {avg_safety_score:.2f}/1.00")
        print(f"   Avg certainty: {(1-avg_uncertainty)*100:.0f}%")
        print(f"   Total hallucinations detected: {sum(hallucination_counts.values())}")
        
        return results
    
    def _run_ablation_study(self, test_data: List[Dict]) -> Dict:
        """Run ablation study"""
        ablation = AblationStudy(
            faiss_manager=self.faiss,
            embedder=self.embedder,
            graph_retriever=self.graph_retriever,
            faiss_index_path=self.config.get('faiss_index_path', '../faiss_index.index'),
            neo4j_uri=self.config.get('neo4j', {}).get('uri', 'bolt://localhost:7687'),
            neo4j_user=self.config.get('neo4j', {}).get('user', 'neo4j'),
            neo4j_password=self.config.get('neo4j', {}).get('password', 'password')
        )
        
        # Convert test data to query format
        queries = [
            {
                'query': qa['question'],
                'relevant_doc_ids': [qa['chunk_id']]
            }
            for qa in test_data
        ]
        
        # Run ablation study
        results = ablation.run_ablation_study(queries)
        
        return results
    
    async def _compare_baselines(self, test_data: List[Dict]) -> Dict:
        """Compare with baseline systems"""
        print("Note: Baseline comparison requires integration with your RAG system")
        print("Returning placeholder results...")
        
        # TODO: Implement actual baseline comparison
        # from baselines.baseline_systems import compare_baselines
        # results = compare_baselines(queries, documents, self.config['api_key'], eval_func)
        
        return {
            'BM25': {'recall@5': 0.0},
            'Dense Retrieval': {'recall@5': 0.0}
        }
    
    def _generate_answer(self, question: str) -> str:
        """Generate answer using your RAG system"""
        try:
            # Use graph retriever if available, otherwise FAISS
            if self.graph_retriever:
                contexts = self.graph_retriever.retrieve(question, top_k=5, use_graph=True)
            else:
                query_emb = self.embedder.embed_texts([question])[0]
                contexts = self.faiss.query(query_emb, top_k=5)
            
            # Generate answer using retrieved contexts
            answer = self.generator.generate_answer(question, contexts, level="Advanced")
            return answer
        except Exception as e:
            print(f"[WARNING] Error generating answer: {e}")
            return f"Error: {str(e)}"
    
    def _generate_answer_with_context(self, question: str) -> tuple:
        """Generate answer with retrieved context"""
        try:
            # Use graph retriever if available, otherwise FAISS
            if self.graph_retriever:
                contexts = self.graph_retriever.retrieve(question, top_k=5, use_graph=True)
            else:
                query_emb = self.embedder.embed_texts([question])[0]
                contexts = self.faiss.query(query_emb, top_k=5)
            
            # Extract text from context chunks
            context_texts = [c.get('metadata', {}).get('text', '') or c.get('text', '') for c in contexts]
            context_texts = [t for t in context_texts if t]  # Filter empty strings
            
            # Generate answer
            answer = self.generator.generate_answer(question, contexts, level="Advanced")
            return answer, context_texts
        except Exception as e:
            print(f"[WARNING] Error generating answer with context: {e}")
            return f"Error: {str(e)}", []
    
    def _generate_report(self):
        """Generate comprehensive text report"""
        report_path = self.output_dir / f"evaluation_report_{self.results['experiment_id']}.txt"
        
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write("="*80 + "\n")
            f.write("RAG SYSTEM EVALUATION REPORT\n")
            f.write("="*80 + "\n\n")
            
            f.write(f"Experiment ID: {self.results['experiment_id']}\n")
            f.write(f"Generated: {datetime.now().isoformat()}\n\n")
            
            # Dataset statistics
            f.write("DATASET STATISTICS\n")
            f.write("-"*80 + "\n")
            for key, value in self.results['dataset_stats'].items():
                f.write(f"{key}: {value}\n")
            f.write("\n")
            
            # Retrieval results
            f.write("RETRIEVAL PERFORMANCE\n")
            f.write("-"*80 + "\n")
            for metric, score in self.results['retrieval_results'].items():
                f.write(f"{metric}: {score:.4f}\n")
            f.write("\n")
            
            # QA results
            f.write("QA PERFORMANCE\n")
            f.write("-"*80 + "\n")
            for metric, score in self.results['qa_results'].items():
                f.write(f"{metric}: {score:.4f}\n")
            f.write("\n")
            
            # Hallucination results
            f.write("HALLUCINATION ANALYSIS\n")
            f.write("-"*80 + "\n")
            for metric, score in self.results['hallucination_results'].items():
                f.write(f"{metric}: {score:.4f}\n")
            f.write("\n")
            
            # Verification results (NEW)
            f.write("VERIFICATION PIPELINE ANALYSIS\n")
            f.write("-"*80 + "\n")
            ver_results = self.results['verification_results']
            if ver_results.get('status') == 'skipped':
                f.write("Verification pipeline was not available during evaluation.\n")
            else:
                f.write(f"Abstention Rate: {ver_results.get('abstention_rate', 0)*100:.2f}%\n")
                f.write(f"Abstention Count: {ver_results.get('abstention_count', 0)}/{ver_results.get('total_examples', 0)}\n")
                f.write(f"Average Safety Score: {ver_results.get('avg_safety_score', 0):.2f}/1.00\n")
                f.write(f"Average Certainty: {ver_results.get('avg_certainty', 0)*100:.1f}%\n")
                f.write(f"Average Uncertainty: {ver_results.get('avg_uncertainty', 0):.3f}\n\n")
                
                f.write("Hallucination Type Distribution:\n")
                hall_dist = ver_results.get('hallucination_distribution', {})
                if hall_dist:
                    for h_type, count in sorted(hall_dist.items(), key=lambda x: x[1], reverse=True):
                        f.write(f"  {h_type}: {count}\n")
                else:
                    f.write("  No hallucinations detected\n")
                f.write("\n")
                
                f.write("Severity Distribution:\n")
                sev_dist = ver_results.get('severity_distribution', {})
                for severity in ['critical', 'high', 'medium', 'low']:
                    count = sev_dist.get(severity, 0)
                    f.write(f"  {severity.capitalize()}: {count}\n")
            f.write("\n")
            
            # Ablation results
            f.write("ABLATION STUDY RESULTS\n")
            f.write("-"*80 + "\n")
            for config, metrics in self.results['ablation_results'].items():
                f.write(f"\n{config}:\n")
                for metric, score in metrics.items():
                    f.write(f"  {metric}: {score:.4f}\n")
            f.write("\n")
        
        print(f"Report saved: {report_path}")
        
        # Also save as JSON
        json_path = self.output_dir / f"evaluation_results_{self.results['experiment_id']}.json"
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(self.results, f, indent=2)
        
        print(f"JSON results saved: {json_path}")
    
    def _generate_visualizations(self):
        """Generate publication-quality visualizations"""
        if not HAS_VISUALIZATION:
            print("Skipping visualizations (matplotlib not installed)")
            return
            
        sns.set_style("whitegrid")
        
        # 1. Ablation study comparison
        if self.results['ablation_results']:
            self._plot_ablation_results()
        
        # 2. Baseline comparison
        if self.results['baseline_comparison']:
            self._plot_baseline_comparison()
        
        # 3. Metric radar chart
        # self._plot_metric_radar()
    
    def _plot_ablation_results(self):
        """Plot ablation study results"""
        if not HAS_VISUALIZATION:
            return
            
        fig, ax = plt.subplots(figsize=(12, 6))
        
        configs = list(self.results['ablation_results'].keys())
        metrics = list(self.results['ablation_results'][configs[0]].keys())
        
        x = range(len(configs))
        width = 0.2
        
        for i, metric in enumerate(metrics):
            values = [self.results['ablation_results'][cfg].get(metric, 0) for cfg in configs]
            ax.bar([xi + i*width for xi in x], values, width, label=metric)
        
        ax.set_xlabel('Configuration')
        ax.set_ylabel('Score')
        ax.set_title('Ablation Study Results')
        ax.set_xticks([xi + width for xi in x])
        ax.set_xticklabels(configs, rotation=45, ha='right')
        ax.legend()
        
        plt.tight_layout()
        plt.savefig(self.output_dir / 'ablation_results.png', dpi=300)
        plt.close()
    
    def _plot_baseline_comparison(self):
        """Plot baseline comparison"""
        if not HAS_VISUALIZATION:
            return
            
        try:
            import pandas as pd
            fig, ax = plt.subplots(figsize=(10, 6))
            
            systems = list(self.results['baseline_comparison'].keys())
            # Add your system
            systems.insert(0, 'Our System (Hybrid RAG)')
            
            metrics = ['recall@5']  # Extend with other metrics
            
            # Placeholder data - replace with actual results
            data = {system: [0.8] for system in systems}
            
            df = pd.DataFrame(data, index=metrics).T
            df.plot(kind='bar', ax=ax)
            
            ax.set_xlabel('System')
            ax.set_ylabel('Score')
            ax.set_title('Baseline Comparison')
            ax.legend(loc='lower right')
            
            plt.tight_layout()
            plt.savefig(self.output_dir / 'baseline_comparison.png', dpi=300)
            plt.close()
        except Exception as e:
            print(f"Error plotting baseline comparison: {e}")
    
    def _plot_metric_radar(self):
        """Plot radar chart of multiple metrics"""
        # Placeholder - implement radar chart
        pass
    
    def _export_latex_tables(self):
        """Export results as LaTeX tables for paper"""
        latex_path = self.output_dir / 'latex_tables.tex'
        
        with open(latex_path, 'w', encoding='utf-8') as f:
            # Retrieval results table
            f.write("\\begin{table}[h]\n")
            f.write("\\centering\n")
            f.write("\\caption{Retrieval Performance}\n")
            f.write("\\begin{tabular}{lr}\n")
            f.write("\\hline\n")
            f.write("Metric & Score \\\\\n")
            f.write("\\hline\n")
            
            for metric, score in self.results['retrieval_results'].items():
                f.write(f"{metric} & {score:.4f} \\\\\n")
            
            f.write("\\hline\n")
            f.write("\\end{tabular}\n")
            f.write("\\end{table}\n\n")
            
            # QA results table
            f.write("\\begin{table}[h]\n")
            f.write("\\centering\n")
            f.write("\\caption{QA Performance}\n")
            f.write("\\begin{tabular}{lr}\n")
            f.write("\\hline\n")
            f.write("Metric & Score \\\\\n")
            f.write("\\hline\n")
            
            for metric, score in self.results['qa_results'].items():
                f.write(f"{metric} & {score:.4f} \\\\\n")
            
            f.write("\\hline\n")
            f.write("\\end{tabular}\n")
            f.write("\\end{table}\n\n")
            
            # Verification pipeline table (NEW)
            ver_results = self.results.get('verification_results', {})
            if ver_results and ver_results.get('status') != 'skipped':
                f.write("\\begin{table}[h]\n")
                f.write("\\centering\n")
                f.write("\\caption{Verification Pipeline Metrics}\n")
                f.write("\\begin{tabular}{lr}\n")
                f.write("\\hline\n")
                f.write("Metric & Value \\\\\n")
                f.write("\\hline\n")
                
                f.write(f"Abstention Rate & {ver_results.get('abstention_rate', 0)*100:.2f}\\% \\\\\n")
                f.write(f"Avg Safety Score & {ver_results.get('avg_safety_score', 0):.3f} \\\\\n")
                f.write(f"Avg Certainty & {ver_results.get('avg_certainty', 0)*100:.1f}\\% \\\\\n")
                
                # Severity distribution
                sev_dist = ver_results.get('severity_distribution', {})
                total_hallucinations = sum(sev_dist.values())
                f.write(f"Total Hallucinations & {total_hallucinations} \\\\\n")
                if sev_dist.get('critical', 0) > 0:
                    f.write(f"Critical Errors & {sev_dist['critical']} \\\\\n")
                if sev_dist.get('high', 0) > 0:
                    f.write(f"High Severity & {sev_dist['high']} \\\\\n")
                
                f.write("\\hline\n")
                f.write("\\end{tabular}\n")
                f.write("\\end{table}\n\n")
        
        print(f"LaTeX tables saved: {latex_path}")


async def main():
    """Run comprehensive evaluation"""
    evaluator = ComprehensiveEvaluator(
        config_file="config.json",
        output_dir="results"
    )
    
    await evaluator.run_full_evaluation()


if __name__ == "__main__":
    asyncio.run(main())
