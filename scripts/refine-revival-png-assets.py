#!/usr/bin/env python3
from pathlib import Path
from PIL import Image, ImageDraw
import hashlib, json, math, shutil
R=Path(__file__).resolve().parents[1]; G=R/'server/public/assets/img/game'; V=R/'server/public/assets/img/revival'; A=R/'server/src/assets.js'
W=H=512
for c in ('resources','tokens','weapons','launchers','ultimates','slayers','gear','crates'):(V/c).mkdir(parents=True,exist_ok=True)

def cv():return Image.new('RGBA',(W,H),(0,0,0,0))
def poly(d,p,f,o,w=7):d.polygon(p,fill=f);d.line(p+[p[0]],fill=o,width=w,joint='curve')
def glow(d,c):
 for r,a in ((180,12),(140,18),(100,26),(62,38)):d.ellipse((256-r,256-r,256+r,256+r),fill=c+(a,))
def sig(d,n,c):
 h=hashlib.sha256(n.encode()).digest()
 for i,v in enumerate(h[:6]):d.rectangle((60+i*18,430-v%35,68+i*18,430),fill=c+(170,))
def save(n,c,im,m):
 p=V/c/f'{n}.png';im.save(p);shutil.copyfile(p,G/f'{n}.png');m[n]={'file':f'{n}.png','source':f'{c}/{n}.png','category':c}

def weapon(n,k,col=(255,92,35),hi=(255,205,105)):
 im=cv();d=ImageDraw.Draw(im,'RGBA');glow(d,col);M=(31,31,36,255);D=(12,12,15,255);a=col+(255,);b=hi+(255,)
 S={'heavycannon':[(65,295),(145,250),(346,211),(430,225),(472,253),(435,290),(300,314),(170,340),(78,330)],'combatshotgun':[(67,300),(166,264),(397,236),(462,251),(432,285),(275,310),(145,334),(78,326)],'supershotgun':[(67,286),(210,250),(429,239),(465,257),(431,286),(207,308),(75,318)],'plasmarifle':[(80,306),(170,264),(366,220),(443,233),(467,265),(422,302),(258,325),(101,332)],'chaingun':[(70,300),(160,258),(326,231),(396,241),(417,294),(330,319),(173,342),(78,330)],'rocketlauncher':[(68,303),(134,263),(372,222),(444,236),(470,260),(438,294),(224,326),(80,331)],'ballista':[(63,293),(203,270),(389,232),(465,248),(451,274),(314,298),(159,313),(70,313)],'gausscannon':[(62,300),(197,262),(407,236),(464,250),(447,283),(282,307),(139,328),(76,324)],'burstrifle':[(68,299),(170,259),(389,236),(452,250),(444,279),(295,305),(149,331),(77,324)]}
 if k=='sentinelhammer':d.rounded_rectangle((224,103,290,391),18,fill=M,outline=a,width=8);poly(d,[(113,131),(397,131),(425,187),(392,243),(123,243),(89,185)],M,a,8)
 else:
  poly(d,S[k],M,a);d.rounded_rectangle((150,310,198,397),10,fill=D,outline=a,width=5)
  if k=='chaingun':
   for y in (232,252,272):d.line((388,y,480,y-12),fill=b,width=8)
  elif k=='supershotgun':d.line((330,247,480,247),fill=b,width=9);d.line((330,273,480,273),fill=b,width=9)
  elif k=='plasmarifle':
   for x in (255,298,341):d.ellipse((x,240,x+28,268),fill=b)
  elif k=='ballista':d.line((168,260,277,204),fill=b,width=9);d.line((168,316,277,357),fill=b,width=9)
  elif k=='gausscannon':d.rectangle((230,228,407,248),fill=D,outline=b,width=5);d.ellipse((195,246,256,307),outline=b,width=6)
  elif k=='rocketlauncher':d.rounded_rectangle((368,225,489,287),20,fill=D,outline=b,width=6)
  else:d.rectangle((330,230,475,258),fill=D,outline=b,width=5)
 sig(d,n,hi);return im

def token(n,t,i):
 P=[((159,82,255),(230,197,255)),((255,90,48),(255,211,121)),((55,170,255),(184,232,255)),((82,220,126),(204,255,219)),((255,170,48),(255,234,154))][i%5];im=cv();d=ImageDraw.Draw(im,'RGBA');glow(d,P[0]);q=[]
 for j in range(6):a=math.radians(j*60-30);q.append((256+153*math.cos(a),256+153*math.sin(a)))
 poly(d,q,(28,18,41,238),P[0]+(255,),10)
 if t in WEAPS:im.alpha_composite(weapon(n+'m',t,P[0],P[1]).resize((260,260),Image.Resampling.LANCZOS),(126,122))
 elif t=='helmet':poly(d,[(202,190),(232,157),(282,157),(315,183),(325,246),(292,301),(221,301),(190,246)],(42,39,49,255),P[1]+(255,),6);d.rectangle((216,215,300,248),fill=P[0]+(220,))
 elif t=='chestplate':poly(d,[(205,172),(308,172),(346,222),(326,315),(187,315),(167,222)],(42,39,49,255),P[1]+(255,),6)
 elif t=='boots':poly(d,[(224,160),(287,166),(298,246),(352,284),(355,320),(174,320),(174,284),(217,247)],(42,39,49,255),P[1]+(255,),6)
 elif t=='gloves':poly(d,[(189,223),(247,180),(322,204),(330,283),(280,323),(204,300)],(42,39,49,255),P[1]+(255,),6)
 else:d.polygon([(256,151),(292,207),(280,331),(232,331),(219,207)],fill=(42,39,49,255),outline=P[1]+(255,))
 sig(d,n,P[1]);return im

def slayer(n,i):
 C=[(255,99,39),(244,184,54),(216,48,36),(109,185,255),(109,197,93),(92,213,255),(255,126,218),(215,65,52),(69,200,116),(60,115,232),(139,75,58),(245,113,65),(159,37,34),(255,117,31),(122,157,192),(220,45,43),(95,130,76),(96,180,220)];c=C[i%18];h=tuple(min(255,x+90) for x in c);im=cv();d=ImageDraw.Draw(im,'RGBA');glow(d,c);w=(i%3)*8;poly(d,[(150-w,222),(172,139-(i%4)*9),(222,101),(291,101),(342,139-(i%4)*9),(365+w,222),(342,354),(300,405),(210,405),(168,354)],(35,33,37,255),c+(255,),8);d.polygon([(183,224),(226,194),(298,194),(333,224),(310,282),(204,282)],fill=(11,19,20,255),outline=h+(255,))
 if i%2:d.rounded_rectangle((203,218,311,249),10,fill=c+(230,),outline=h+(255,),width=4)
 else:d.polygon([(201,224),(247,211),(239,246),(205,249)],fill=c+(255,));d.polygon([(267,211),(314,224),(309,249),(275,246)],fill=c+(255,))
 if i%3==0:d.polygon([(166,175),(119,114),(143,216)],fill=(50,44,48,255),outline=h+(255,));d.polygon([(347,175),(394,114),(370,216)],fill=(50,44,48,255),outline=h+(255,))
 elif i%3==1:d.polygon([(238,111),(256,48),(276,111)],fill=c+(255,),outline=h+(255,))
 sig(d,n,h);return im

def gear(n,s,p):
 PAL={'cultist':((133,53,37),(255,127,58)),'uac':((70,116,105),(132,230,189)),'demonic':((135,28,31),(255,69,51)),'exultian':((175,114,35),(255,215,105)),'hellfire':((167,48,22),(255,129,41)),'cryo':((52,119,167),(149,229,255)),'cyro':((48,101,157),(122,211,255)),'barrage':((90,82,118),(202,166,255)),'charged':((44,105,167),(99,199,255)),'radioactive':((73,120,45),(170,240,80)),'arc':((75,62,158),(138,119,255)),'allresist':((100,83,72),(236,203,168))};b,h=PAL[s];im=cv();d=ImageDraw.Draw(im,'RGBA');glow(d,h);M=b+(255,);H=h+(255,);D=(24,22,25,255)
 if p=='helmet':poly(d,[(160,214),(181,137),(231,103),(288,103),(337,137),(359,214),(339,342),(298,390),(211,390),(173,342)],M,H,8);d.polygon([(188,217),(225,190),(292,190),(330,217),(307,273),(205,273)],fill=D,outline=H)
 elif p=='torso':poly(d,[(166,131),(221,102),(290,102),(346,131),(395,212),(355,395),(157,395),(116,212)],M,H,8)
 elif p=='boots':poly(d,[(208,100),(303,113),(317,248),(410,298),(421,363),(115,363),(113,305),(194,252)],M,H,8)
 else:poly(d,[(143,222),(222,176),(336,204),(365,312),(292,385),(166,347)],M,H,8)
 nset=sum(map(ord,s))%4
 if nset==0:d.polygon([(256,178),(285,232),(256,286),(228,232)],fill=H)
 elif nset==1:d.line((212,205,256,244,303,205),fill=H,width=9)
 elif nset==2:
  for x in (205,256,307):d.polygon([(x,147),(x+12,98),(x+26,154)],fill=H)
 else:d.line((222,184,275,228,242,267,301,315),fill=H,width=10)
 sig(d,n,h);return im

def simple(n,kind,col,hi):
 im=cv();d=ImageDraw.Draw(im,'RGBA');glow(d,col);A=col+(255,);B=hi+(255,);M=(35,35,40,255)
 if kind=='crate':poly(d,[(121,188),(190,122),(394,122),(433,174),(433,344),(365,405),(131,405),(90,344),(90,191)],M,A,8);d.rectangle((219,250,304,326),fill=(20,20,23,255),outline=B,width=7)
 elif kind=='launcher':d.rounded_rectangle((160,145,352,362),48,fill=M,outline=A,width=8);d.ellipse((215,205,297,287),fill=B)
 elif kind=='resource':d.polygon([(256,62),(358,168),(323,399),(256,445),(181,394),(143,184)],fill=col+(190,),outline=B);d.line((256,62,256,441),fill=A,width=8)
 sig(d,n,hi);return im

WEAPS={'heavycannon','combatshotgun','supershotgun','plasmarifle','chaingun','rocketlauncher','ballista','gausscannon','burstrifle','sentinelhammer'};M={}
RES={'store_crystalsingle_01':((255,60,38),(255,205,92)),'store_coinssingle_01':((226,135,22),(255,225,114)),'store_slayerorbssingle_01':((155,82,255),(231,199,255)),'store_tech_single_01':((45,205,230),(170,249,255)),'store_equipmentcrate_key_single_01':((90,208,123),(205,255,216)),'store_weaponcrate_key_single_01':((255,104,45),(255,213,118)),'store_specialcrate_key_single_01':((170,75,255),(238,202,255)),'icon_ability_xp_up_major':((75,208,121),(212,255,220)),'store_skinshards_01':((190,80,255),(239,205,255)),'store_argentenergy_01':((43,131,255),(187,234,255))}
for n,(c,h) in RES.items():save(n,'resources',simple(n,'resource',c,h),M)
for i,k in enumerate(sorted(WEAPS)):
 n=f'wpn_icon_{k}_01';save(n,'weapons',weapon(n,k),M);t=f'store_tokensingle_{k}_01';save(t,'tokens',token(t,k,i),M)
for i,t in enumerate(('helmet','chestplate','boots','gloves','launcher','ultimate')):
 n=f'store_tokensingle_{t}_01';save(n,'tokens',token(n,t,i+10),M)
save('store_token_allrandom_tier_01','tokens',token('store_token_allrandom_tier_01','ultimate',19),M)
SL=['slayerdefault','slayergold','slayercrimson','slayerclassicmarine','slayerzombie','slayerhailfire','slayerdoomicorn','slayerronin','slayerhoppingmad','slayerslaytriot','slayermarauder','slayergibbo','slayerdemonic','slayerjackoslayer','slayerpioneer','slayersanta','slayersurvivalist','slayerwintherin']
for i,s in enumerate(SL):
 n=f'slay_icon_events_{s}_01';save(n,'slayers',slayer(n,i),M);q=f'store_shard_{s}_01';save(q,'tokens',token(q,'helmet',i+20),M)
for s in ('cultist','uac','demonic','exultian','hellfire','cryo','cyro','barrage','charged','radioactive','arc'):
 for p in ('helmet','torso','boots','gloves'):
  n=f'gear_icon_{s}_{p}_01';save(n,'gear',gear(n,s,p),M)
save('gear_icon_allresist_gloves_01','gear',gear('gear_icon_allresist_gloves_01','allresist','gloves'),M)
L=['lch_icon_explosive_fraggrenade_01','lch_icon_fire_flamebelch_01','lch_icon_ice_icebomb_01','lch_icon_plasma_arcgrenade_01','lch_icon_toxic_acidspit_01']
for i,n in enumerate(L):c=[(255,105,41),(255,70,28),(68,171,255),(142,91,255),(96,199,74)][i];save(n,'launchers',simple(n,'launcher',c,tuple(min(255,x+100) for x in c)),M)
U={'ult_icon_bfg_01':'heavycannon','ult_icon_chainsaw_01':'chaingun','ult_icon_crucible_01':'sentinelhammer','ult_icon_unmaykr_01':'plasmarifle','ult_icon_samuraisword_01':'sentinelhammer'}
for i,(n,k) in enumerate(U.items()):c=[(70,255,130),(255,90,39),(255,55,38),(155,80,255),(112,190,255)][i];save(n,'ultimates',weapon(n,k,c,tuple(min(255,x+80) for x in c)),M)
CR=['crt_icon_weaponcrate_01','crt_icon_equipmentcrate_01','crt_icon_specialcrate_01','crt_icon_prizetrackcrate_01','crt_icon_fireelementalcrate_01','crt_icon_iceelementalcrate_01','crt_icon_toxicelementalcrate_01','crt_icon_plasmaelementalcrate_01','crt_icon_explosiveelementalcrate_01','crt_icon_adcrate_01']
for i,n in enumerate(CR):c=[(255,109,46),(113,240,151),(191,103,255),(255,183,54),(255,103,34),(142,225,255),(163,237,76),(152,112,255),(255,150,48),(208,208,218)][i];save(n,'crates',simple(n,'crate',c,tuple(min(255,x+70) for x in c)),M)
if A.exists():
 s=A.read_text();s=s.replace("alias(['skin_shards', 'shards', 'skin_unlock_shards'], 'Shards de skin', null, 'currency')","alias(['skin_shards', 'shards', 'skin_unlock_shards'], 'Shards de skin', 'store_skinshards_01', 'currency')");s=s.replace("alias(['argent_energy', 'argent', 'token_slayer_argent-energy'], 'Argent Energy', null, 'energy')","alias(['argent_energy', 'argent', 'token_slayer_argent-energy'], 'Argent Energy', 'store_argentenergy_01', 'energy')");s=s.replace("alias([`shard_${tag}`, `shard_${tag.replace(/_?slayer$/, '')}`], `Shards ${display}`, null, 'currency')","alias([`shard_${tag}`, `shard_${tag.replace(/_?slayer$/, '')}`], `Shards ${display}`, `store_shard_${icon}_01`, 'currency')");s=s.replace("burst_rifle: null, sentinel_hammer: null","burst_rifle: 'burstrifle', sentinel_hammer: 'sentinelhammer'");A.write_text(s)
(G/'manifest.json').write_text(json.dumps({'origin':'Revival original artwork; dedicated image per known alias','files':M},indent=2));(V/'manifest.json').write_text(json.dumps({'origin':'100% original Revival artwork','count':len(M),'files':M},indent=2))
seen={}
for n in M:
 h=hashlib.sha256((G/f'{n}.png').read_bytes()).hexdigest()
 if h in seen:raise SystemExit(f'duplicate {n} == {seen[h]}')
 seen[h]=n
print(f'Refined {len(M)} aliases; duplicate PNGs: 0')
