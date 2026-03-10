"""Missing methods analysis: flag complementary methods the paper didn't use.

Given the methods identified in a paper, look up what other methods exist in
the same ecosystem/toolkit and flag methods that could address resolution gaps
the primary method can't.

This module is primarily a curated registry with lookup logic — no embedding
infrastructure needed.
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional


# ---------------------------------------------------------------------------
# Resolution types — what kind of signal a method can resolve
# ---------------------------------------------------------------------------

RESOLUTION_TYPES: Dict[str, str] = {
    "genome_wide": "Measures aggregate signal across entire genome",
    "site_specific": "Measures signal at individual sites/positions",
    "gene_wide": "Measures signal per gene/region",
    "temporal": "Measures changes over time",
    "cross_sectional": "Compares across samples at one timepoint",
    "aggregate": "Summarizes across individuals/populations",
    "individual": "Resolves individual-level variation",
    "spatial": "Resolves spatial structure or location",
    "network": "Resolves interaction/network structure",
    "single_cell": "Resolves individual cell-level variation",
}


# ---------------------------------------------------------------------------
# Method registry — curated ecosystems of related analytical methods
# ---------------------------------------------------------------------------

METHOD_REGISTRY: Dict[str, Dict] = {
    "hyphy": {
        "name": "HyPhy (Hypothesis Testing using Phylogenies)",
        "methods": {
            "relax": {
                "name": "RELAX",
                "resolution": ["genome_wide"],
                "detects": "Shifts in selection intensity distribution (K parameter)",
                "limitations": [
                    "Cannot detect site-specific changes",
                    "Cannot detect indels",
                    "Sensitive to branch length",
                ],
            },
            "meme": {
                "name": "MEME",
                "resolution": ["site_specific"],
                "detects": "Episodic positive selection at individual sites",
                "limitations": ["Requires sufficient branch diversity"],
            },
            "fel": {
                "name": "FEL",
                "resolution": ["site_specific"],
                "detects": "Pervasive selection at individual sites",
                "limitations": ["Assumes constant selection across branches"],
            },
            "fubar": {
                "name": "FUBAR",
                "resolution": ["site_specific"],
                "detects": "Pervasive selection (Bayesian, faster than FEL)",
                "limitations": ["Same branch assumption as FEL"],
            },
            "busted": {
                "name": "BUSTED",
                "resolution": ["gene_wide"],
                "detects": "Gene-wide test for positive selection on foreground branches",
                "limitations": ["Gene-level, not site-level"],
            },
            "absrel": {
                "name": "aBSREL",
                "resolution": ["gene_wide"],
                "detects": "Branch-site adaptive evolution",
                "limitations": [
                    "Exploratory, high false positive rate without correction",
                ],
            },
            "prime": {
                "name": "PRIME",
                "resolution": ["site_specific"],
                "detects": "Property-informed models of evolution at sites",
                "limitations": ["Requires amino acid data"],
            },
            "fade": {
                "name": "FADE",
                "resolution": ["site_specific"],
                "detects": "Directional selection on amino acid properties",
                "limitations": ["Requires amino acid alignment"],
            },
            "slac": {
                "name": "SLAC",
                "resolution": ["site_specific"],
                "detects": "Counting-based dN/dS at individual sites",
                "limitations": [
                    "Conservative (low power)",
                    "Requires many sequences",
                ],
            },
        },
    },
    "beast": {
        "name": "BEAST (Bayesian Evolutionary Analysis)",
        "methods": {
            "beast_phylodynamics": {
                "name": "BEAST Phylodynamics",
                "resolution": ["temporal"],
                "detects": "Divergence times, population dynamics, molecular clock",
                "limitations": ["Clock model assumptions", "Prior sensitivity"],
            },
            "bssvs": {
                "name": "BSSVS",
                "resolution": ["temporal", "cross_sectional"],
                "detects": "Discrete phylogeographic diffusion",
                "limitations": ["Requires location metadata"],
            },
            "skyline": {
                "name": "Bayesian Skyline / Skygrid",
                "resolution": ["temporal"],
                "detects": "Effective population size through time",
                "limitations": [
                    "Requires temporal signal in sequences",
                    "Sensitive to sampling scheme",
                ],
            },
            "dta": {
                "name": "Discrete Trait Analysis",
                "resolution": ["temporal", "cross_sectional"],
                "detects": "Ancestral state reconstruction for discrete traits",
                "limitations": ["Symmetric vs asymmetric rate assumptions"],
            },
        },
    },
    "r_phylogenetics": {
        "name": "R Phylogenetics Ecosystem",
        "methods": {
            "pgls": {
                "name": "PGLS",
                "resolution": ["cross_sectional"],
                "detects": "Trait correlations controlling for phylogeny",
                "limitations": ["Assumes Brownian motion or OU process"],
            },
            "diversitree": {
                "name": "diversitree",
                "resolution": ["temporal"],
                "detects": "State-dependent diversification rates",
                "limitations": ["Model complexity, data requirements"],
            },
            "phytools": {
                "name": "phytools",
                "resolution": ["cross_sectional", "temporal"],
                "detects": "Ancestral state reconstruction, rate mapping",
                "limitations": ["Visualization-oriented, limited statistical tests"],
            },
            "ape_ace": {
                "name": "ape::ace",
                "resolution": ["cross_sectional"],
                "detects": "Ancestral character estimation (ML and Bayesian)",
                "limitations": ["Simple models only"],
            },
        },
    },
    "paml": {
        "name": "PAML (Phylogenetic Analysis by Maximum Likelihood)",
        "methods": {
            "codeml_site": {
                "name": "codeml site models (M1a/M2a, M7/M8)",
                "resolution": ["site_specific"],
                "detects": "Sites under positive selection via dN/dS",
                "limitations": [
                    "Sensitive to alignment quality",
                    "Assumes single tree topology",
                ],
            },
            "codeml_branch": {
                "name": "codeml branch models",
                "resolution": ["gene_wide"],
                "detects": "Lineage-specific dN/dS shifts",
                "limitations": ["Requires a priori branch labelling"],
            },
            "codeml_branch_site": {
                "name": "codeml branch-site models",
                "resolution": ["site_specific", "gene_wide"],
                "detects": "Sites under selection on specific lineages",
                "limitations": [
                    "Computationally intensive",
                    "Sensitive to guide tree",
                ],
            },
            "baseml": {
                "name": "baseml",
                "resolution": ["genome_wide"],
                "detects": "Nucleotide substitution models, rates",
                "limitations": ["No selection-specific inference"],
            },
        },
    },
    "sklearn": {
        "name": "scikit-learn",
        "methods": {
            "pca": {
                "name": "PCA",
                "resolution": ["aggregate"],
                "detects": "Principal axes of variation",
                "limitations": ["Linear only", "No causal interpretation"],
            },
            "clustering": {
                "name": "Clustering (k-means, DBSCAN, etc.)",
                "resolution": ["aggregate"],
                "detects": "Group structure in data",
                "limitations": [
                    "Sensitive to distance metric and hyperparameters",
                ],
            },
            "random_forest": {
                "name": "Random Forest / Gradient Boosting",
                "resolution": ["individual"],
                "detects": "Predictive patterns, feature importance",
                "limitations": ["Black box, overfitting risk"],
            },
            "umap_tsne": {
                "name": "UMAP / t-SNE",
                "resolution": ["aggregate"],
                "detects": "Non-linear low-dimensional embeddings",
                "limitations": [
                    "Distances not preserved globally",
                    "Hyperparameter-sensitive",
                ],
            },
        },
    },
    "deseq": {
        "name": "Differential Expression Ecosystem",
        "methods": {
            "deseq2": {
                "name": "DESeq2",
                "resolution": ["individual", "gene_wide"],
                "detects": "Differentially expressed genes",
                "limitations": ["Requires replicates", "Distributional assumptions"],
            },
            "edger": {
                "name": "edgeR",
                "resolution": ["individual", "gene_wide"],
                "detects": "Differentially expressed genes (negative binomial)",
                "limitations": ["Requires replicates"],
            },
            "gsea": {
                "name": "GSEA",
                "resolution": ["aggregate"],
                "detects": "Pathway-level enrichment",
                "limitations": ["Depends on pathway database quality"],
            },
            "limma": {
                "name": "limma-voom",
                "resolution": ["individual", "gene_wide"],
                "detects": "Differential expression via linear models",
                "limitations": [
                    "Originally designed for microarray",
                    "Voom transformation needed for RNA-seq",
                ],
            },
        },
    },
    "single_cell": {
        "name": "Single-Cell RNA-seq Ecosystem",
        "methods": {
            "scanpy": {
                "name": "Scanpy / Seurat",
                "resolution": ["single_cell", "aggregate"],
                "detects": "Cell clustering, trajectory, marker genes",
                "limitations": ["Dropout noise", "Batch effects"],
            },
            "scvelo": {
                "name": "scVelo",
                "resolution": ["single_cell", "temporal"],
                "detects": "RNA velocity, dynamic trajectory inference",
                "limitations": ["Requires spliced/unspliced counts"],
            },
            "cellrank": {
                "name": "CellRank",
                "resolution": ["single_cell", "temporal"],
                "detects": "Cell fate probabilities from velocity",
                "limitations": ["Depends on scVelo quality"],
            },
        },
    },
    "population_genetics": {
        "name": "Population Genetics Ecosystem",
        "methods": {
            "fst": {
                "name": "Fst / Hudson Fst",
                "resolution": ["aggregate", "genome_wide"],
                "detects": "Population differentiation",
                "limitations": [
                    "Sensitive to sample size",
                    "Cannot distinguish selection from drift",
                ],
            },
            "tajima_d": {
                "name": "Tajima's D",
                "resolution": ["genome_wide", "gene_wide"],
                "detects": "Deviations from neutral evolution",
                "limitations": [
                    "Confounded by demography",
                    "Low resolution",
                ],
            },
            "ehh_ihs": {
                "name": "EHH / iHS",
                "resolution": ["site_specific", "genome_wide"],
                "detects": "Extended haplotype homozygosity (recent sweeps)",
                "limitations": ["Requires phased haplotype data"],
            },
            "admixture": {
                "name": "ADMIXTURE / STRUCTURE",
                "resolution": ["aggregate", "individual"],
                "detects": "Population structure and admixture proportions",
                "limitations": [
                    "Assumes Hardy-Weinberg within clusters",
                    "K selection is subjective",
                ],
            },
            "sfs": {
                "name": "Site Frequency Spectrum (SFS) methods",
                "resolution": ["aggregate", "genome_wide"],
                "detects": "Demographic history, selection signatures",
                "limitations": [
                    "Requires many unrelated samples",
                    "Sensitive to ascertainment bias",
                ],
            },
        },
    },
    "network_analysis": {
        "name": "Network / Graph Analysis Ecosystem",
        "methods": {
            "wgcna": {
                "name": "WGCNA",
                "resolution": ["network", "gene_wide"],
                "detects": "Co-expression modules, hub genes",
                "limitations": [
                    "Requires many samples (>15)",
                    "Arbitrary soft-threshold choice",
                ],
            },
            "string_ppi": {
                "name": "STRING / PPI networks",
                "resolution": ["network"],
                "detects": "Protein-protein interaction patterns",
                "limitations": ["Database bias toward well-studied genes"],
            },
            "grn_inference": {
                "name": "GRN inference (GENIE3, SCENIC)",
                "resolution": ["network", "individual"],
                "detects": "Gene regulatory network topology",
                "limitations": [
                    "High false positive rate",
                    "Requires careful validation",
                ],
            },
        },
    },
    "structural_biology": {
        "name": "Structural Biology / Molecular Dynamics",
        "methods": {
            "alphafold": {
                "name": "AlphaFold / ColabFold",
                "resolution": ["site_specific", "individual"],
                "detects": "Predicted 3D protein structure",
                "limitations": [
                    "Static structure only",
                    "Low confidence in disordered regions",
                ],
            },
            "md_simulation": {
                "name": "Molecular Dynamics",
                "resolution": ["site_specific", "temporal"],
                "detects": "Dynamic conformational changes, binding",
                "limitations": [
                    "Computationally expensive",
                    "Force field accuracy",
                    "Timescale limitations",
                ],
            },
            "docking": {
                "name": "Molecular Docking (AutoDock, etc.)",
                "resolution": ["site_specific"],
                "detects": "Predicted binding poses and affinities",
                "limitations": [
                    "Scoring function accuracy",
                    "Rigid receptor assumption",
                ],
            },
        },
    },
    "metagenomics": {
        "name": "Metagenomics / Microbiome Ecosystem",
        "methods": {
            "qiime2": {
                "name": "QIIME 2",
                "resolution": ["aggregate", "individual"],
                "detects": "Microbial community composition (16S/ITS)",
                "limitations": [
                    "Amplicon bias",
                    "Species-level resolution limited",
                ],
            },
            "metaphlan": {
                "name": "MetaPhlAn / Kraken2",
                "resolution": ["individual", "aggregate"],
                "detects": "Taxonomic profiling from shotgun metagenomics",
                "limitations": ["Database-dependent", "Unknown taxa missed"],
            },
            "humann": {
                "name": "HUMAnN",
                "resolution": ["aggregate", "gene_wide"],
                "detects": "Functional profiling of microbial communities",
                "limitations": ["Pathway database completeness"],
            },
        },
    },
    "epigenomics": {
        "name": "Epigenomics Ecosystem",
        "methods": {
            "bismark": {
                "name": "Bismark / methylation calling",
                "resolution": ["site_specific", "genome_wide"],
                "detects": "DNA methylation at CpG sites",
                "limitations": [
                    "Bisulfite conversion incomplete",
                    "Cannot distinguish 5mC from 5hmC",
                ],
            },
            "chipseq": {
                "name": "ChIP-seq peak calling (MACS2, etc.)",
                "resolution": ["site_specific", "genome_wide"],
                "detects": "Histone modifications, TF binding sites",
                "limitations": [
                    "Antibody quality critical",
                    "Input control needed",
                ],
            },
            "atacseq": {
                "name": "ATAC-seq",
                "resolution": ["site_specific", "genome_wide"],
                "detects": "Chromatin accessibility",
                "limitations": [
                    "Tn5 insertion bias",
                    "Cell type heterogeneity",
                ],
            },
        },
    },
    "bayesian_statistics": {
        "name": "Bayesian Statistical Ecosystem",
        "methods": {
            "stan": {
                "name": "Stan / brms",
                "resolution": ["individual", "aggregate"],
                "detects": "Posterior distributions for arbitrary models",
                "limitations": [
                    "Prior specification required",
                    "Convergence diagnostics needed",
                ],
            },
            "inla": {
                "name": "R-INLA",
                "resolution": ["individual", "spatial"],
                "detects": "Approximate Bayesian inference for latent Gaussian models",
                "limitations": ["Restricted to LGCP model class"],
            },
            "abc": {
                "name": "Approximate Bayesian Computation",
                "resolution": ["aggregate"],
                "detects": "Parameter inference for simulator-based models",
                "limitations": [
                    "Summary statistic choice critical",
                    "Computationally expensive",
                ],
            },
        },
    },
    "causal_inference": {
        "name": "Causal Inference Ecosystem",
        "methods": {
            "mendelian_randomization": {
                "name": "Mendelian Randomization",
                "resolution": ["aggregate", "individual"],
                "detects": "Causal effects using genetic instruments",
                "limitations": [
                    "Instrument validity assumptions",
                    "Horizontal pleiotropy",
                ],
            },
            "diff_in_diff": {
                "name": "Difference-in-Differences",
                "resolution": ["temporal", "aggregate"],
                "detects": "Causal treatment effects with panel data",
                "limitations": [
                    "Parallel trends assumption",
                    "Requires pre/post data",
                ],
            },
            "propensity_score": {
                "name": "Propensity Score Matching",
                "resolution": ["individual"],
                "detects": "Treatment effect controlling for observables",
                "limitations": [
                    "Cannot control for unobserved confounders",
                    "Positivity assumption",
                ],
            },
        },
    },
}


# ---------------------------------------------------------------------------
# Aliases — common names and abbreviations that should resolve to registry keys
# ---------------------------------------------------------------------------

_METHOD_ALIASES: Dict[str, tuple] = {
    # HyPhy methods
    "relax": ("hyphy", "relax"),
    "relax framework": ("hyphy", "relax"),
    "hyphy relax": ("hyphy", "relax"),
    "meme": ("hyphy", "meme"),
    "hyphy meme": ("hyphy", "meme"),
    "mixed effects model of evolution": ("hyphy", "meme"),
    "fel": ("hyphy", "fel"),
    "fixed effects likelihood": ("hyphy", "fel"),
    "fubar": ("hyphy", "fubar"),
    "fast unconstrained bayesian approximation": ("hyphy", "fubar"),
    "busted": ("hyphy", "busted"),
    "branch-site unrestricted statistical test": ("hyphy", "busted"),
    "absrel": ("hyphy", "absrel"),
    "adaptive branch-site": ("hyphy", "absrel"),
    "prime": ("hyphy", "prime"),
    "fade": ("hyphy", "fade"),
    "slac": ("hyphy", "slac"),
    "single-likelihood ancestor counting": ("hyphy", "slac"),
    # BEAST
    "beast": ("beast", "beast_phylodynamics"),
    "beast2": ("beast", "beast_phylodynamics"),
    "bssvs": ("beast", "bssvs"),
    "bayesian skyline": ("beast", "skyline"),
    "skyline": ("beast", "skyline"),
    "skygrid": ("beast", "skyline"),
    "bayesian skygrid": ("beast", "skyline"),
    "discrete trait analysis": ("beast", "dta"),
    # PAML
    "paml": ("paml", "codeml_site"),
    "codeml": ("paml", "codeml_site"),
    "baseml": ("paml", "baseml"),
    "branch-site model": ("paml", "codeml_branch_site"),
    "branch model": ("paml", "codeml_branch"),
    "site model": ("paml", "codeml_site"),
    "m1a": ("paml", "codeml_site"),
    "m2a": ("paml", "codeml_site"),
    "m7": ("paml", "codeml_site"),
    "m8": ("paml", "codeml_site"),
    # R phylogenetics
    "pgls": ("r_phylogenetics", "pgls"),
    "phylogenetic generalized least squares": ("r_phylogenetics", "pgls"),
    "diversitree": ("r_phylogenetics", "diversitree"),
    "phytools": ("r_phylogenetics", "phytools"),
    "ace": ("r_phylogenetics", "ape_ace"),
    # scikit-learn
    "pca": ("sklearn", "pca"),
    "principal component analysis": ("sklearn", "pca"),
    "k-means": ("sklearn", "clustering"),
    "kmeans": ("sklearn", "clustering"),
    "dbscan": ("sklearn", "clustering"),
    "random forest": ("sklearn", "random_forest"),
    "gradient boosting": ("sklearn", "random_forest"),
    "xgboost": ("sklearn", "random_forest"),
    "umap": ("sklearn", "umap_tsne"),
    "t-sne": ("sklearn", "umap_tsne"),
    "tsne": ("sklearn", "umap_tsne"),
    # Differential expression
    "deseq2": ("deseq", "deseq2"),
    "deseq": ("deseq", "deseq2"),
    "edger": ("deseq", "edger"),
    "gsea": ("deseq", "gsea"),
    "gene set enrichment": ("deseq", "gsea"),
    "limma": ("deseq", "limma"),
    "limma-voom": ("deseq", "limma"),
    "voom": ("deseq", "limma"),
    # Single cell
    "scanpy": ("single_cell", "scanpy"),
    "seurat": ("single_cell", "scanpy"),
    "scvelo": ("single_cell", "scvelo"),
    "rna velocity": ("single_cell", "scvelo"),
    "cellrank": ("single_cell", "cellrank"),
    # Population genetics
    "fst": ("population_genetics", "fst"),
    "tajima": ("population_genetics", "tajima_d"),
    "tajima's d": ("population_genetics", "tajima_d"),
    "ihs": ("population_genetics", "ehh_ihs"),
    "ehh": ("population_genetics", "ehh_ihs"),
    "extended haplotype": ("population_genetics", "ehh_ihs"),
    "admixture": ("population_genetics", "admixture"),
    "structure": ("population_genetics", "admixture"),
    "site frequency spectrum": ("population_genetics", "sfs"),
    "sfs": ("population_genetics", "sfs"),
    # Network
    "wgcna": ("network_analysis", "wgcna"),
    "string": ("network_analysis", "string_ppi"),
    "ppi": ("network_analysis", "string_ppi"),
    "genie3": ("network_analysis", "grn_inference"),
    "scenic": ("network_analysis", "grn_inference"),
    # Structural
    "alphafold": ("structural_biology", "alphafold"),
    "colabfold": ("structural_biology", "alphafold"),
    "molecular dynamics": ("structural_biology", "md_simulation"),
    "md simulation": ("structural_biology", "md_simulation"),
    "autodock": ("structural_biology", "docking"),
    "molecular docking": ("structural_biology", "docking"),
    # Metagenomics
    "qiime": ("metagenomics", "qiime2"),
    "qiime2": ("metagenomics", "qiime2"),
    "metaphlan": ("metagenomics", "metaphlan"),
    "kraken": ("metagenomics", "metaphlan"),
    "kraken2": ("metagenomics", "metaphlan"),
    "humann": ("metagenomics", "humann"),
    # Epigenomics
    "bismark": ("epigenomics", "bismark"),
    "methylation": ("epigenomics", "bismark"),
    "chip-seq": ("epigenomics", "chipseq"),
    "chipseq": ("epigenomics", "chipseq"),
    "macs2": ("epigenomics", "chipseq"),
    "atac-seq": ("epigenomics", "atacseq"),
    "atacseq": ("epigenomics", "atacseq"),
    # Bayesian
    "stan": ("bayesian_statistics", "stan"),
    "brms": ("bayesian_statistics", "stan"),
    "r-inla": ("bayesian_statistics", "inla"),
    "inla": ("bayesian_statistics", "inla"),
    "abc": ("bayesian_statistics", "abc"),
    "approximate bayesian computation": ("bayesian_statistics", "abc"),
    # Causal
    "mendelian randomization": ("causal_inference", "mendelian_randomization"),
    "mr": ("causal_inference", "mendelian_randomization"),
    "difference-in-differences": ("causal_inference", "diff_in_diff"),
    "diff-in-diff": ("causal_inference", "diff_in_diff"),
    "propensity score": ("causal_inference", "propensity_score"),
}


def detect_methods(text: str) -> List[str]:
    """Auto-detect method names mentioned in paper text.

    Scans for known method names and aliases from the registry.
    Returns deduplicated list of matched method names.
    """
    found = []
    seen_targets = set()
    text_lower = text.lower()

    for alias, (eco_key, meth_key) in _METHOD_ALIASES.items():
        target = (eco_key, meth_key)
        if target in seen_targets:
            continue
        # Check if alias appears in text (word-boundary-ish)
        if re.search(r'\b' + re.escape(alias) + r'\b', text_lower):
            meth = METHOD_REGISTRY[eco_key]["methods"][meth_key]
            found.append(meth["name"])
            seen_targets.add(target)

    # Also check method names directly
    for eco_key, eco in METHOD_REGISTRY.items():
        for meth_key, meth in eco["methods"].items():
            target = (eco_key, meth_key)
            if target in seen_targets:
                continue
            name_lower = meth["name"].lower()
            if re.search(r'\b' + re.escape(name_lower) + r'\b', text_lower):
                found.append(meth["name"])
                seen_targets.add(target)

    return found


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _normalize(name: str) -> str:
    """Lowercase, strip, collapse whitespace."""
    return re.sub(r"\s+", " ", name.strip().lower())


def _match_method(query: str) -> Optional[tuple]:
    """Fuzzy-match a method name against the alias table and registry.

    Tries, in order:
    1. Exact alias match (after normalization).
    2. Substring match against aliases (query contained in alias or alias in query).
    3. Substring match against registry method names.

    Returns ``(ecosystem_key, method_key)`` or ``None``.
    """
    q = _normalize(query)
    if not q:
        return None

    # 1. Exact alias match
    if q in _METHOD_ALIASES:
        return _METHOD_ALIASES[q]

    # 2. Substring match against aliases (prefer shorter alias = more specific)
    candidates: List[tuple] = []
    for alias, target in _METHOD_ALIASES.items():
        if alias in q or q in alias:
            candidates.append((len(alias), target))
    if candidates:
        # Sort by alias length descending — longer matches are more specific
        candidates.sort(key=lambda x: -x[0])
        return candidates[0][1]

    # 3. Substring match against registry method names
    for eco_key, eco in METHOD_REGISTRY.items():
        for meth_key, meth in eco["methods"].items():
            meth_name = _normalize(meth["name"])
            if q in meth_name or meth_name in q:
                return (eco_key, meth_key)

    return None


def _get_method_info(eco_key: str, meth_key: str) -> Dict:
    """Retrieve full method info from the registry."""
    eco = METHOD_REGISTRY[eco_key]
    meth = eco["methods"][meth_key]
    return {
        "name": meth["name"],
        "ecosystem": eco_key,
        "ecosystem_name": eco["name"],
        "method_key": meth_key,
        "resolution": list(meth["resolution"]),
        "detects": meth["detects"],
        "limitations": list(meth["limitations"]),
    }


def _resolution_gap_priority(
    required: List[str],
    covered: List[str],
    method_resolution: List[str],
) -> str:
    """Determine priority of a missing method based on resolution coverage.

    Returns "high", "medium", or "low".
    """
    if not required:
        return "medium"

    # High priority: method addresses a resolution gap the paper needs
    gaps = set(required) - set(covered)
    if gaps & set(method_resolution):
        return "high"

    # Medium: method is in the same ecosystem (reviewer might expect it)
    # (caller already filters to same-ecosystem, so medium is the baseline)
    return "medium"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def check_missing_methods(
    methods_used: List[str],
    question_resolution: Optional[List[str]] = None,
) -> Dict:
    """Check if complementary methods from same ecosystems were used.

    Args:
        methods_used: Method names as they appear in the paper text.
            Matched fuzzily against the registry (case-insensitive,
            substring matching, alias lookup).
        question_resolution: Resolution types the paper's research
            question requires (e.g., ``["site_specific"]``).  Used to
            determine priority of missing methods.

    Returns:
        Dict with keys:
        - ``methods_identified``: methods from the input that matched the
          registry, with ecosystem and resolution info.
        - ``missing_complementary``: methods in the same ecosystem(s) that
          were *not* used, ranked by relevance.
        - ``resolution_coverage``: summary of required vs covered vs gap
          resolution types.
    """
    required = list(question_resolution) if question_resolution else []

    # --- Identify used methods ---
    identified: List[Dict] = []
    identified_keys: set = set()  # (eco_key, meth_key) pairs already matched
    ecosystems_used: set = set()

    for raw_name in methods_used:
        match = _match_method(raw_name)
        if match is None:
            continue
        eco_key, meth_key = match
        if (eco_key, meth_key) in identified_keys:
            continue
        identified_keys.add((eco_key, meth_key))
        ecosystems_used.add(eco_key)
        info = _get_method_info(eco_key, meth_key)
        identified.append({
            "name": info["name"],
            "matched_from": raw_name,
            "ecosystem": eco_key,
            "resolution": info["resolution"],
        })

    # --- Resolution coverage ---
    covered = sorted({
        r
        for item in identified
        for r in item["resolution"]
    })
    gaps = sorted(set(required) - set(covered)) if required else []

    # --- Find missing complementary methods ---
    missing: List[Dict] = []
    for eco_key in ecosystems_used:
        eco = METHOD_REGISTRY[eco_key]
        for meth_key, meth in eco["methods"].items():
            if (eco_key, meth_key) in identified_keys:
                continue

            priority = _resolution_gap_priority(
                required, covered, meth["resolution"],
            )

            # Build the why_relevant explanation
            meth_resolutions = set(meth["resolution"])
            if gaps and (meth_resolutions & set(gaps)):
                filled = sorted(meth_resolutions & set(gaps))
                why = (
                    f"Paper question requires {', '.join(filled)} resolution "
                    f"but only {', '.join(covered) if covered else 'no'} "
                    f"resolution method(s) used"
                )
            else:
                why = (
                    f"Same ecosystem ({eco['name']}); "
                    f"adds {', '.join(meth['resolution'])} resolution"
                )

            missing.append({
                "name": meth["name"],
                "ecosystem": eco_key,
                "method_key": meth_key,
                "resolution": list(meth["resolution"]),
                "detects": meth["detects"],
                "limitations": list(meth["limitations"]),
                "why_relevant": why,
                "priority": priority,
            })

    # Sort: high priority first, then alphabetically
    priority_order = {"high": 0, "medium": 1, "low": 2}
    missing.sort(key=lambda x: (priority_order.get(x["priority"], 9), x["name"]))

    return {
        "methods_identified": identified,
        "missing_complementary": missing,
        "resolution_coverage": {
            "required": required,
            "covered": covered,
            "gaps": gaps,
        },
    }


def list_ecosystems() -> List[Dict]:
    """Return a summary of all registered method ecosystems.

    Useful for displaying available ecosystems to users or for
    building method-selection UIs.
    """
    result: List[Dict] = []
    for eco_key, eco in sorted(METHOD_REGISTRY.items()):
        methods = sorted(eco["methods"].keys())
        result.append({
            "key": eco_key,
            "name": eco["name"],
            "method_count": len(methods),
            "methods": [eco["methods"][m]["name"] for m in methods],
        })
    return result


def get_ecosystem_methods(ecosystem: str) -> List[Dict]:
    """Return all methods in a given ecosystem with full details.

    Args:
        ecosystem: Registry key (e.g., ``"hyphy"``, ``"beast"``).

    Returns:
        List of method info dicts, or empty list if ecosystem not found.
    """
    eco = METHOD_REGISTRY.get(ecosystem)
    if eco is None:
        return []
    return [
        _get_method_info(ecosystem, meth_key)
        for meth_key in sorted(eco["methods"].keys())
    ]
