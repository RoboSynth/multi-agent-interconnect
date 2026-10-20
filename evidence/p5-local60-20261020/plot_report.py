"""Plots only measured results, with failure and timing contracts stated."""
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

OUTPUT=Path(__file__).resolve().parent/'publication'
data=json.loads((OUTPUT/'summary.json').read_text(encoding='utf-8'))
pairs=json.loads((OUTPUT/'paired-M2v2-M0.json').read_text(encoding='utf-8'))
confirmed_pairs=[row for row in pairs if row['both_confirmed']]
methods=['MR','M0','M1','M2v2']
colors=['#9a8172','#68727d','#2878b5','#278064']
fig,axes=plt.subplots(2,2,figsize=(12,8),layout='constrained')
ax=axes[0,0]
counts=[data['methods'][method]['recovery_confirmed'] for method in methods]
bars=ax.bar(methods,counts,color=colors)
ax.bar_label(bars,labels=[f'{count}/15' for count in counts],padding=3)
ax.set_ylim(0,17);ax.set_ylabel('Strict acceptance passed')
ax.set_title('30 s / 10 complete workflows required',loc='left',fontsize=11)
ax=axes[0,1]
fixed=np.array([row['M0_seconds'] for row in confirmed_pairs]);ranked=np.array([row['M2v2_seconds'] for row in confirmed_pairs])
for index,pair in enumerate(confirmed_pairs):
    ax.plot([0,1],[fixed[index],ranked[index]],color='#c5d2d9',linewidth=.9,zorder=1)
ax.scatter(np.zeros(len(confirmed_pairs)),fixed,color=colors[1],s=25,zorder=2,label='M0')
ax.scatter(np.ones(len(confirmed_pairs)),ranked,color=colors[3],s=25,zorder=2,label='M2v2')
ax.set_xticks([0,1],['M0','M2v2']);ax.set_xlim(-.3,1.3)
ax.set_ylabel('Elapsed seconds, includes final verification')
ratio=data['paired_M2v2_vs_M0']['median_paired_elapsed_ratio']
ax.set_title(f'{len(confirmed_pairs)}/15 confirmed pairs; paired median ratio = {ratio:.3f}',loc='left',fontsize=11)
ax=axes[1,0]
values=[data['methods'][method]['weighted_probe_cost'] for method in methods]
bars=ax.bar(methods,values,color=colors);ax.bar_label(bars,padding=3)
ax.set_ylabel('Observation cost (all 15 attempted cells)')
ax.set_ylim(0,max(values)*1.18)
ax.set_title('1 per probe, 2 per blocking-session probe',loc='left',fontsize=11)
ax=axes[1,1]
values=[data['methods'][method]['sensitive_blocking_session_observations'] for method in methods]
bars=ax.bar(methods,values,color=colors);ax.bar_label(bars,padding=3)
ax.set_ylabel('Blocking-session observations')
ax.set_ylim(0,max(values)*1.18 if max(values) else 1)
ax.set_title('Declared resource domains, not legal companies',loc='left',fontsize=11)
for ax in axes.flat:
    ax.spines[['top','right']].set_visible(False)
    ax.grid(axis='y',alpha=.2);ax.set_axisbelow(True)
fig.suptitle('P5: local paired scheduling evaluation (5 faults x 4 methods x 3 repeats)',fontsize=14)
fig.supxlabel('60 terminal cells; one interrupted attempt excluded from costs. Failed cells remain in cost totals.\nMR has disclosed 504 and verification-window defects. The overall time criterion is not met.',fontsize=9)
fig.savefig(OUTPUT/'comparison.png',dpi=180)
fig.savefig(OUTPUT/'comparison.svg')
print(str(OUTPUT/'comparison.png'))
