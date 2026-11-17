from pathlib import Path
import re, shutil, urllib.parse, json
from PIL import Image
root=Path.cwd(); out=Path(__file__).parent
s=next((out.parent/'input').glob('*.md')).read_text(encoding='utf-8')
s='\n'.join(x for x in s.splitlines() if not x.startswith(('> **编辑说明','> **发布前说明','> 发布前最后检查')))
rows=[]
def picture(m):
 line=m.group(0); label=re.search(r'图 ([\d-]+) ([^】]+)',line)
 n,title=label.groups()
 urls=re.findall(r'https://github.com/[^)]+',line)
 if not urls:
  return '**图 '+n+' '+title+'：待补。PR #10 尚未合并，最终类图须审核通过后补入。**'
 src=urllib.parse.unquote(urls[0].split('/blob/main/')[1]); p=root/src
 if not p.exists(): return '**图 '+n+' '+title+'：待补，仓库缺少对应文件。**'
 with Image.open(p) as im:
  im.load(); fmt=im.format; size=im.size
 name='figure-'+n+'.'+fmt.lower().replace('jpeg','jpg'); shutil.copy2(p,out/'assets'/name)
 caption=line.split('插入博客后配文字说明：')[-1] if '插入博客后配文字说明：' in line else ''
 rows.append((n,title,src,'assets/'+name,str(size)+' '+fmt+'；完整解码通过；文字可读性待人工终审'))
 return f'![{title}](assets/{name})\n\n*图 {n} {title}*\n\n{caption}\n'
s=re.sub(r'^> .*【配图待补[^\n]*',picture,s,flags=re.M)
s=re.sub(r'### 5.4 协作证据（待插图）.*?(?=### 5.5)', '### 5.4 协作证据\n\n协作过程可查阅 [PR 全部记录](https://github.com/yz-Yezi-Genm/CodeMind-FZU/pulls?q=is%3Apr)、[#1 文件修订](https://github.com/yz-Yezi-Genm/CodeMind-FZU/pull/1/files)、[#7 提交记录](https://github.com/yz-Yezi-Genm/CodeMind-FZU/pull/7/commits)及 [#11 原型交付](https://github.com/yz-Yezi-Genm/CodeMind-FZU/pull/11)。截图操作清单随核验报告提供。\n\n',s,flags=re.S)
s=s.replace('仓库贡献可查，博客补具体截图','仓库提交记录可查')
s=s.replace('### 6.1 逐周开发计划','以上贡献表的姓名与账号对应沿用提交署名；未补齐的学号须本人确认。\n\n### 6.1 逐周开发计划')
s=s.replace('## 六、后续开发计划（拟议）','## 六、后续开发计划（拟议，全部安排待团队确认）')
s=s.replace('截至本次核验，','2026-11-09 经 GitHub 实时查询，PR #10 为 open、未合并，当前 2 次提交，头提交 `57dc34fd2c01144d031691b34779740c9e6ea5b7`；更新时间为北京时间 18:22:30。未提供此前头提交基准，不能判定是否相对上次新增提交。其说明仍要求同步 #3 后重建 PDF。\n\n截至本次核验，')
(out/'blog_final_local.md').write_text(s,encoding='utf-8')
web=re.sub(r'\]\(assets/([^)]*)\)',r'](https://REPLACE-WITH-CNBLOGS-IMAGE.invalid/\1)',s)
(out/'blog_final_cnblogs.md').write_text(web,encoding='utf-8')
(out/'image_manifest.md').write_text('# 图片清单\n\n|图号|名称|原始路径|输出路径|核验结果|\n|---|---|---|---|---|\n'+'\n'.join('|'+ '|'.join(r)+'|' for r in rows)+'\n\n引用位置为正文同图号所在章节。图 3-6 缺少已合并最终版，未制作替代图。所有外链须上传博客园后替换。\n',encoding='utf-8')
links=[]
for url in sorted(set(re.findall(r'https://[^\s)]+',s))):
 status='待人工验证匿名访问'
 if '/blob/main/' in url or '/tree/main/' in url:
  path=urllib.parse.unquote(re.split(r'/(?:blob|tree)/main/',url)[1]); status='本地存在' if (root/path).exists() else '本地缺失'
 links.append('|'+url+'|'+status+'|')
(out/'link_audit.md').write_text('# 链接核查\n\n本地存在不等于在线匿名访问通过。\n\n|地址|结果|\n|---|---|\n'+'\n'.join(links),encoding='utf-8')
print('Copied images:',len(rows),'remaining markers:',s.count('【配图待补】'))
