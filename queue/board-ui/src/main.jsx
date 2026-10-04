import React, { useEffect, useMemo, useState } from 'react';
import { createRoot } from 'react-dom/client';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import {
  Alert, Breadcrumb, Button, Card, ConfigProvider, Empty, Image, Input, Layout, Menu,
  Progress, Select, Statistic, Steps, Table, Tag, Typography,
} from 'antd';
import zhCN from 'antd/locale/zh_CN';
import {
  AppstoreOutlined, DashboardOutlined, FileTextOutlined,
  FolderOpenOutlined, LinkOutlined, PlayCircleOutlined, MenuOutlined,
} from '@ant-design/icons';
import 'antd/dist/reset.css';
import './board.css';

const { Header, Sider, Content } = Layout;
const { Title, Text } = Typography;
const board = JSON.parse(document.getElementById('board-data').textContent);
const projects = board.projects || [];
const currentProjects = projects.filter((project) => project.kind === 'project');
const archiveProjects = projects.filter((project) => project.kind === 'archive');
const getProject = (path) => projects.find((project) => project.path === path);
const percent = (part, whole) => whole ? Math.round(part / whole * 100) : 0;
const localLink = (path) => `../${path.split('/').map(encodeURIComponent).join('/')}`;
const fileSize = (bytes) => bytes >= 1048576 ? `${(bytes / 1048576).toFixed(1)} MB` : bytes >= 1024 ? `${(bytes / 1024).toFixed(1)} KB` : `${bytes} B`;
const viewLabels = { progress: '进度', documents: '剧本与资料', assets: '素材资产', materials: '分镜用料', prompts: '提示词', files: '文件台账' };

function routeFromHash() {
  const params = new URLSearchParams(window.location.hash.slice(1));
  const path = params.get('project');
  const view = params.get('view');
  const project = getProject(path);
  const doc = params.get('doc');
  return {
    path: project ? path : null,
    view: viewLabels[view] ? view : 'progress',
    doc: findDocument(project, doc)?.key || null,
  };
}

function documentsFor(project) {
  return [...(project?.document_items || []), ...(board.workspace_documents || [])];
}

function findDocument(project, value) {
  if (!project || !value) return null;
  return documentsFor(project).find((item) => item.exists && (item.key === value || item.path === value));
}

function documentHash(path, key) {
  return `#project=${encodeURIComponent(path)}&view=documents&doc=${encodeURIComponent(key)}`;
}

function statusColor(stage) {
  if (stage.includes('已合成') || stage.includes('通过')) return 'success';
  if (stage.includes('待') || stage.includes('返工')) return 'warning';
  if (stage.includes('审核')) return 'processing';
  return 'default';
}

function StateTag({ stage }) {
  return <Tag color={statusColor(stage)}>{stage}</Tag>;
}

function StatCard({ title, value, suffix, note }) {
  return (
    <Card size="small" className="stat-card">
      <Statistic title={title} value={value} suffix={suffix} />
      {note && <div className="stat-note">{note}</div>}
    </Card>
  );
}

function taskRows(projectList) {
  return projectList.flatMap((project) => [
    ...(project.points_21 || []).map((item, index) => ({
      key: `${project.path}:points:${index}`, project, lane: 'points_21', item,
    })),
    ...(project.anytime || []).map((item, index) => ({
      key: `${project.path}:anytime:${index}`, project, lane: 'anytime', item,
    })),
  ]);
}

function taskName(item) {
  if (item.work === 'rework_shots') return '分镜返工';
  if (item.task === 'final_online_edit') return '在线剪辑';
  return item.work || item.task || '待办任务';
}

function stateLabel(state) {
  const labels = {
    intake: '待准备', preparing: '准备中', ready: '已就绪', editing: '剪辑中',
    exporting_to_canvas: '正在导出到画布', waiting_browser: '等待浏览器',
    waiting_balance: '等待费用授权 / 余额', retry_needed: '待返工',
    waiting_21_window: '等待积分窗口',
    waiting_dependency_and_input: '等待依赖与素材',
    waiting_dependency: '等待依赖',
    waiting_input: '等待素材',
    running: '进行中',
    review: '待审核',
    done: '已完成',
  };
  return labels[state] || state || '未登记';
}

function TaskTable({ records, goToProject, compact = false }) {
  const columns = [
    ...(!compact ? [{
      title: '作品', key: 'project', width: 250,
      render: (_, row) => <Button type="link" onClick={() => goToProject(row.project.path)}>{row.project.title}</Button>,
    }] : []),
    { title: '任务', key: 'task', render: (_, row) => taskName(row.item) },
    {
      title: '通道', key: 'lane', width: 140,
      render: (_, row) => <Tag color={row.lane === 'points_21' ? 'gold' : 'blue'}>{row.lane === 'points_21' ? `积分 · ${board.credit_start}` : 'Anytime'}</Tag>,
    },
    { title: '状态', key: 'state', width: 160, render: (_, row) => stateLabel(row.item.state) },
    {
      title: '镜头 / 依赖', key: 'detail',
      render: (_, row) => row.item.shots?.length
        ? row.item.shots.map((number) => `#${number}`).join('  ')
        : (row.item.depends_on || row.item.missing?.join('、') || '—'),
    },
  ];
  return (
    <Table
      size="small"
      columns={columns}
      dataSource={records}
      rowKey="key"
      pagination={false}
      scroll={{ x: compact ? 640 : 900 }}
      locale={{ emptyText: <Empty description="当前没有排队任务" /> }}
    />
  );
}

function Overview({ goToProject }) {
  const [projectQuery, setProjectQuery] = useState('');
  const allTasks = useMemo(() => taskRows(projects), []);
  const visibleProjects = projects.filter((project) => project.title.toLocaleLowerCase().includes(projectQuery.trim().toLocaleLowerCase()));
  const pendingShots = currentProjects.reduce((sum, project) => sum + project.retake_numbers.length, 0);
  const assembled = archiveProjects.filter((project) => project.story_file).length;
  const audioBlocked = currentProjects.filter((project) => project.final_waiting && project.audio?.file_status === 'missing');
  const columns = [
    {
      title: '作品', dataIndex: 'title', key: 'title', width: 320,
      render: (title, project) => (
        <div className="work-name">
          <Button type="link" onClick={() => goToProject(project.path)}>{title}</Button>
          <Text type="secondary">{project.kind === 'archive' ? '历史样片' : '当前项目'}</Text>
        </div>
      ),
      filters: [
        { text: '当前项目', value: 'project' },
        { text: '历史样片', value: 'archive' },
      ],
      onFilter: (value, project) => project.kind === value,
    },
    { title: '阶段', dataIndex: 'stage', key: 'stage', width: 170, render: (stage) => <StateTag stage={stage} /> },
    {
      title: '分镜进度', key: 'progress', width: 250,
      render: (_, project) => (
        <div className="table-progress">
          <Progress
            percent={percent(project.kind === 'archive' ? project.generated : project.passed, project.expected_shots)}
            size="small"
            showInfo={false}
          />
          <Text type="secondary">
            {project.kind === 'archive' ? '已生成' : '审片通过'} {project.kind === 'archive' ? project.generated : project.passed}/{project.expected_shots || '—'}
          </Text>
        </div>
      ),
    },
    {
      title: '任务 / 素材', key: 'work', width: 220,
      render: (_, project) => project.kind === 'archive'
        ? (project.story_file ? '已有合成版' : '最新分镜待重剪')
        : `${project.points_21.length + project.anytime.length} 项队列任务 · ${project.assets.total} 项三视图`,
    },
    {
      title: '查看', key: 'action', width: 92,
      render: (_, project) => <Button type="link" onClick={() => goToProject(project.path)}>详情</Button>,
    },
  ];
  return (
    <>
      <div className="page-heading">
        <div><div className="eyebrow">PORTFOLIO</div><Title level={2}>作品总览</Title><Text type="secondary">查看正在制作的项目和已有样片，点击作品进入单独进度页。</Text></div>
        <Tag color="processing">积分通道窗口 {board.credit_start} · {board.timezone}</Tag>
      </div>
      <div className="stat-grid">
        <StatCard title="全部作品" value={projects.length} note={`${currentProjects.length} 个当前项目 · ${archiveProjects.length} 个历史样片`} />
        <StatCard title="活跃队列项目" value={currentProjects.filter((project) => project.anytime.length || project.points_21.length).length} note="按任务队列统计" />
        <StatCard title="待返工镜头" value={pendingShots} note="21 点队列逐镜核价" />
        <StatCard title="已有合成样片" value={assembled} note="历史样片中的现行版本" />
      </div>
      {audioBlocked.length > 0 && (
        <Alert
          type="warning"
          showIcon
          className="page-alert"
          title={`${audioBlocked.length} 个作品的最终剪辑缺少可用音源`}
          description="可在作品详情查看音源状态；镜头生成仍按原队列继续。"
          action={<Button size="small" onClick={() => goToProject(audioBlocked[0].path)}>查看作品</Button>}
        />
      )}
      <Card title={`全部作品 · ${visibleProjects.length}`} className="section-card" extra={<Input aria-label="搜索作品" className="project-search" placeholder="搜索作品名称" allowClear value={projectQuery} onChange={(event) => setProjectQuery(event.target.value)} />}>
        <Table
          size="middle"
          columns={columns}
          dataSource={visibleProjects}
          rowKey="path"
          pagination={{ pageSize: 12, hideOnSinglePage: true }}
          scroll={{ x: 980 }}
          locale={{ emptyText: <Empty description="暂无作品" /> }}
        />
      </Card>
      <div className="two-column">
        <Card title="任务队列" className="section-card">
          <TaskTable records={allTasks} goToProject={goToProject} />
        </Card>
        <Card title="调度与费用" className="section-card">
          <div className="policy-row"><Tag className="policy-tag" color="blue">Anytime</Tag><span>素材和依赖就绪后开展零新增费用工作。</span></div>
          <div className="policy-row"><Tag className="policy-tag" color="gold">{board.credit_start}</Tag><span>积分任务按配置窗口、当前授权、现场报价与余额核验。</span></div>
          <div className="policy-row"><Tag className="policy-tag" color={board.execution_policy?.allow_existing_runninghub_points_at_21_00 ? "gold" : "default"}>积分策略</Tag><span>{board.execution_policy?.allow_existing_runninghub_points_at_21_00 ? "配置允许积分；执行前仍须确认当前用户授权。" : "未配置积分授权；默认预算为 0。"}</span></div>
          <div className="policy-row"><Tag className="policy-tag" color="red">需暂停</Tag><span>现金扣款、充值或其他平台付费。</span></div>
        </Card>
      </div>
    </>
  );
}

function ProjectHeading({ project, goToOverview }) {
  return (
    <div className="page-heading">
      <div>
        <div className="eyebrow">{project.kind === 'archive' ? 'ARCHIVED SAMPLE' : 'ACTIVE PROJECT'}</div>
        <div className="title-row"><Title level={2}>{project.title}</Title><StateTag stage={project.stage} /></div>
        <Text type="secondary">{project.kind === 'archive' ? 'RunningHub MiniMax H3 历史样片' : '独立项目 · 单作品单画布'}</Text>
      </div>
      <div className="heading-actions">
        <Button onClick={goToOverview}>返回总览</Button>
        {project.canvas && <Button icon={<LinkOutlined />} href={project.canvas} target="_blank">RunningHub 画布</Button>}
        {project.story_file && <Button type="primary" icon={<PlayCircleOutlined />} href={localLink(project.story_file)} target="_blank">查看成片</Button>}
      </div>
    </div>
  );
}

function ShotTable({ project }) {
  const columns = [
    { title: '镜号', dataIndex: 'number', key: 'number', width: 82, render: (number) => String(number).padStart(2, '0') },
    {
      title: '状态', dataIndex: 'state', key: 'state', width: 170,
      filters: [
        { text: '未提交', value: 'planned' },
        { text: '运行中', value: 'running' },
        { text: '待审片', value: 'review' },
        { text: '已通过', value: 'passed' },
        { text: '需重做', value: 'redo' },
        { text: '已生成', value: 'generated' },
        { text: '缺文件', value: 'missing' },
      ],
      onFilter: (value, row) => row.state === value,
      render: (state, row) => <Tag color={state === 'passed' ? 'success' : state === 'redo' || state === 'missing' ? 'warning' : 'processing'}>{row.verdict}</Tag>,
    },
    { title: '长度', dataIndex: 'duration', key: 'duration', width: 120 },
    { title: '审核记录 / 素材', dataIndex: 'notes', key: 'notes' },
    {
      title: '视频', dataIndex: 'file', key: 'file', width: 110,
      render: (file) => file ? <Button type="link" href={localLink(file)} target="_blank">播放片段</Button> : '—',
    },
  ];
  return (
    <Table
      size="small"
      columns={columns}
      dataSource={project.shots}
      rowKey="number"
      pagination={{ pageSize: 8, showSizeChanger: false }}
      scroll={{ x: 870 }}
      locale={{ emptyText: <Empty description="还没有分镜记录" /> }}
    />
  );
}

function ProjectDocs({ project, openDocument }) {
  const names = {
    'AGENTS.md': '项目规范', 'research.md': '研究', 'script.md': '剧本',
    'storyboard.md': '分镜', 'prompts/shot-prompts.md': '逐镜提示词', 'shot_audit.md': '审片记录',
  };
  const existing = Object.entries(project.documents || {}).filter(([, exists]) => exists);
  return (
    <Card title="项目资料" className="section-card">
      <div className="doc-links">
        {existing.map(([file]) => <Button key={file} icon={<FileTextOutlined />} onClick={() => openDocument(file)}>{names[file]}</Button>)}
        {project.source_document && <Button icon={<FileTextOutlined />} onClick={() => openDocument(project.source_document)}>样片来源记录</Button>}
        {project.reference_image && <Button icon={<LinkOutlined />} href={localLink(project.reference_image)} target="_blank">画布截图</Button>}
      </div>
    </Card>
  );
}

function ActiveProject({ project, goToProject, openDocument }) {
  const total = project.expected_shots || project.shot_count;
  const tasks = taskRows([project]);
  const audio = project.audio || {};
  const audioMissing = audio.file_status === 'missing';
  const fullAudit = total > 0 && project.passed >= total && project.redo === 0;
  const stepItems = [
    { title: '剧本与分镜', description: project.documents?.['script.md'] && project.documents?.['storyboard.md'] ? '已记录' : '准备中', status: project.documents?.['script.md'] && project.documents?.['storyboard.md'] ? 'finish' : 'process' },
    { title: '参考资产', description: project.assets.total ? `${project.assets.total} 项预览 · ${project.assets.uploaded || 0} 项登记上传` : '准备中', status: project.assets.total && project.assets.uploaded >= project.assets.total ? 'finish' : 'wait' },
    { title: '镜头生成', description: project.generated ? `${project.generated} 镜已生成` : '未开始', status: project.generated >= total && total ? 'finish' : 'wait' },
    { title: '逐镜审核', description: `${project.passed} 通过 · ${project.redo} 待返工`, status: fullAudit ? 'finish' : 'process' },
    { title: '在线剪辑', description: project.final_waiting ? '等待镜头与音源' : '尚未登记', status: 'wait' },
  ];
  const currentStep = Math.max(0, stepItems.findIndex((item) => item.status !== 'finish'));
  return (
    <>
      <div className="stat-grid">
        <StatCard title="已通过分镜" value={project.passed} suffix={`/ ${total || '—'}`} note="逐镜审片结论" />
        <StatCard title="待返工镜头" value={project.retake_numbers.length || project.redo} note={project.retake_numbers.length ? `镜号 ${project.retake_numbers.join('、')}` : '暂无排队镜头'} />
        <StatCard title="三视图资产" value={project.assets.total} note="人物、场景和道具" />
        <StatCard title="当前队列任务" value={tasks.length} note="Anytime 与积分队列" />
      </div>
      {project.retake_numbers.length > 0 && (
        <Alert type="warning" showIcon className="page-alert" title={`${project.retake_numbers.length} 个镜头等待积分窗口返工`} description={`镜号 ${project.retake_numbers.join('、')}。提交前按 RunningHub 当前页面核对费用和积分余额。`} />
      )}
      <Card title="制作流程" className="section-card">
        <Steps current={currentStep} items={stepItems} size="small" responsive />
        <div className="section-progress"><Text type="secondary">逐镜审核进度</Text><Progress percent={percent(project.passed, total)} /></div>
      </Card>
      <div className="two-column">
        <Card title="任务队列" className="section-card">
          <TaskTable records={tasks} goToProject={goToProject} compact />
        </Card>
        <Card title="前置资产" className="section-card">
          {project.assets.total ? (
            <div className="asset-grid">
              <Statistic title="人物" value={project.assets.characters} />
              <Statistic title="场景" value={project.assets.scenes} />
              <Statistic title="道具" value={project.assets.props} />
              <Statistic title="画布参考节点" value={project.assets.canvas_nodes} />
            </div>
          ) : <Empty description="尚无三视图资产矩阵" />}
        </Card>
      </div>
      <Card title="音频素材" className="section-card" extra={audio.song && <Tag color={audioMissing ? 'warning' : 'success'}>{audioMissing ? '缺可剪辑音频' : '文件已登记'}</Tag>}>
        {audio.song ? (
          <>
            <div className="audio-line"><strong>{audio.artist}《{audio.song}》</strong><Text type="secondary">{audio.album} · {audio.duration}</Text></div>
            <div className="audio-line"><Text type="secondary">视频剪辑使用权</Text><Tag color={audio.sync_rights_status === 'unverified' ? 'warning' : 'success'}>{audio.sync_rights_status === 'unverified' ? '未核实' : audio.sync_rights_status}</Tag></div>
            <div className="doc-links">
              {(audio.sources || []).map((source) => <Button key={source.url} className="audio-source-link" type="link" href={source.url} target="_blank">{source.label}</Button>)}
              <Button onClick={() => openDocument('assets/audio/source.yaml')}>音源记录</Button>
            </div>
          </>
        ) : <Empty description="项目没有登记音频需求或音源" />}
      </Card>
      <Card title="逐镜审核" className="section-card" extra={<Text type="secondary">{project.shot_count} 镜有记录 · 可按状态筛选</Text>}>
        <ShotTable project={project} />
      </Card>
      <ProjectDocs project={project} openDocument={openDocument} />
    </>
  );
}

function ArchiveProject({ project, openDocument }) {
  return (
    <>
      <div className="stat-grid archive-stats">
        <StatCard title="分镜文件" value={project.generated} suffix={`/ ${project.expected_shots}`} note="历史样片素材" />
        <StatCard title="现行合成版" value={project.story_file ? '已保存' : '待重剪'} note={project.story_file ? '可打开预览' : '旧版合成早于最新分镜'} />
        <StatCard title="RunningHub 画布" value={project.canvas ? '已记录' : '未记录'} note="按现有资料显示" />
      </div>
      <Alert
        className="page-alert"
        type={project.story_file ? 'info' : 'warning'}
        showIcon
        title={project.story_file ? '历史样片已有合成版' : '最新三段分镜尚未重新合成'}
        description="三段分镜文件已留存；这批样片没有独立的逐镜审片记录，因此这里显示生成与合成状态。"
      />
      <Card title="分镜素材" className="section-card" extra={<Text type="secondary">每镜约 5 秒</Text>}>
        <ShotTable project={project} />
      </Card>
      <ProjectDocs project={project} openDocument={openDocument} />
    </>
  );
}

function AssetImage({ asset, size = 64 }) {
  return asset?.image
    ? <Image src={localLink(asset.image)} alt={`${asset.id} ${asset.name}`} width={size} height={size} className="asset-thumb" />
    : <div className="asset-placeholder" style={{ width: size, height: size }}>无本地图片</div>;
}

function AssetChip({ asset }) {
  return (
    <div className="asset-chip" title={asset.name}>
      <AssetImage asset={asset} size={48} />
      <div><strong>{asset.id}</strong><span>{asset.category}</span></div>
    </div>
  );
}

function ReferenceChip({ reference, assetMap }) {
  const asset = assetMap[reference.asset_id];
  return <div className="asset-chip" title={reference.name}>
    <AssetImage asset={{ ...asset, image: reference.image, name: reference.name, id: reference.asset_id || '—' }} size={48} />
    <div><strong>{reference.asset_id || '未匹配'}</strong><span>{reference.name}</span></div>
  </div>;
}

function SectionHeading({ eyebrow, title, description }) {
  return <div className="section-heading"><div className="eyebrow">{eyebrow}</div><Title level={3}>{title}</Title><Text type="secondary">{description}</Text></div>;
}

function DocumentLibrary({ project, initialDoc, openDocument }) {
  const documents = documentsFor(project);
  const [query, setQuery] = useState('');
  useEffect(() => setQuery(''), [project.path]);
  const visibleDocuments = documents.filter((item) => `${item.title} ${item.key} ${item.category}`.toLocaleLowerCase().includes(query.trim().toLocaleLowerCase()));
  const defaultDoc = documents.find((item) => item.key === 'script.md' && item.exists) || documents.find((item) => item.exists);
  const selectedDoc = findDocument(project, initialDoc) || defaultDoc;
  function docUrl(url) {
    if (!url) return '#';
    if (/^(https?:|mailto:)/i.test(url)) return url;
    if (/^[a-z][a-z0-9+.-]*:/i.test(url)) return '#';
    return new URL(url, new URL(localLink(selectedDoc.path), window.location.href)).href;
  }
  function markdownLink(href, children) {
    const resolved = docUrl(href);
    const linkedDoc = documents.find((item) => item.exists && item.path && docUrlForPath(item.path) === resolved.split('#')[0]);
    return linkedDoc
      ? <a href={documentHash(project.path, linkedDoc.key)} onClick={(event) => { event.preventDefault(); openDocument(linkedDoc.key); }}>{children}</a>
      : <a href={resolved} target="_blank" rel="noreferrer">{children}</a>;
  }
  function docUrlForPath(path) {
    return new URL(localLink(path), window.location.href).href;
  }
  return <>
    <SectionHeading eyebrow="CREATIVE DOCUMENTS" title="剧本与创作资料" description="从创意方案、研究、剧本到分镜与审片，按项目固定位置统一浏览。" />
    {project.kind === 'archive' && <Alert className="page-alert" type="info" showIcon title="历史样片仅留存分镜方案" description="这批样片没有独立剧本和研究文档；这里展示已有原始记录，不推断缺失内容。" />}
    <div className="stat-grid document-stats">
      <StatCard title="已登记文档" value={documents.filter((item) => item.exists).length} note={`共规划 ${documents.length} 个文档位置`} />
      <StatCard title="剧本" value={documents.some((item) => item.key === 'script.md' && item.exists) ? '已保存' : '未登记'} note="项目原文可在右侧阅读" />
      <StatCard title="分镜" value={documents.some((item) => item.key === 'storyboard.md' && item.exists) || project.kind === 'archive' ? '已保存' : '未登记'} note="逐镜创作与镜头结构" />
      <StatCard title="资产矩阵" value={documents.some((item) => item.key === 'assets/asset-matrix.md' && item.exists) ? '已保存' : '未登记'} note="对应人物、场景和道具" />
    </div>
    <div className="document-layout">
      <Card title={`资料目录 · ${documents.length}`} className="section-card document-index">
        <Input aria-label="搜索项目文档" placeholder="搜索文档或资产提示词" allowClear value={query} onChange={(event) => setQuery(event.target.value)} />
        <div className="document-entry-list">
          {visibleDocuments.map((item) => <button type="button" key={item.key} disabled={!item.exists} className={`document-entry${selectedDoc?.key === item.key ? ' is-current' : ''}`} onClick={() => openDocument(item.key)}><span><strong>{item.title}</strong><small>{item.category} · {item.exists ? '已登记' : '未建立'}</small></span><span className="document-entry-mark">{item.exists ? '查看' : '—'}</span></button>)}
          {!visibleDocuments.length && <Empty description="没有匹配的文档" />}
        </div>
      </Card>
      {selectedDoc ? <Card className="section-card document-preview" title={selectedDoc.title}>
        <div className="document-meta"><Tag>{selectedDoc.category}</Tag><span>{selectedDoc.path}</span><span>{fileSize(selectedDoc.bytes)}</span><span>更新于 {selectedDoc.modified?.replace('T', ' ')}</span></div>
        {selectedDoc.path.endsWith('.md') ? <div className="markdown-body"><ReactMarkdown remarkPlugins={[remarkGfm]} components={{ a: ({ href, children }) => markdownLink(href, children), img: ({ src, alt }) => <img src={docUrl(src)} alt={alt || ''} /> }}>{selectedDoc.content}</ReactMarkdown></div> : <pre className="document-code">{selectedDoc.content}</pre>}
      </Card> : <Card className="section-card"><Empty description="尚无可阅读的项目文档" /></Card>}
    </div>
  </>;
}

function FileRegistry({ project, openDocument }) {
  const files = project.inventory || [];
  const [query, setQuery] = useState('');
  useEffect(() => setQuery(''), [project.path]);
  const filtered = files.filter((item) => item.path.toLocaleLowerCase().includes(query.trim().toLocaleLowerCase()));
  const categories = [...new Set(files.map((item) => item.category))];
  const columns = [
    { title: '文件', key: 'file', width: 390, render: (_, item) => <div className="registry-file">{/\.(png|jpe?g|webp|gif|svg)$/i.test(item.name) && <AssetImage asset={{ id: item.name, name: item.name, image: item.path }} size={42} />}<div><strong>{item.name}</strong><Text type="secondary">{item.path}</Text></div></div> },
    { title: '类别', dataIndex: 'category', key: 'category', width: 150, filters: categories.map((value) => ({ text: value, value })), onFilter: (value, item) => item.category === value },
    { title: '版本', key: 'version', width: 90, render: (_, item) => item.version ? `v${item.version}` : '—' },
    { title: '大小', key: 'size', width: 100, render: (_, item) => fileSize(item.bytes) },
    { title: '更新', key: 'modified', width: 175, render: (_, item) => item.modified.replace('T', ' ') },
    { title: '操作', key: 'open', width: 90, render: (_, item) => findDocument(project, item.path) ? <Button type="link" onClick={() => openDocument(item.path)}>阅读</Button> : <Button type="link" href={localLink(item.path)} target="_blank">打开</Button> },
  ];
  return <>
    <SectionHeading eyebrow="FILE REGISTRY" title="作品文件台账" description="按固定目录查看本作品的文档、提示词、图像、音频、视频和交付物。" />
    <div className="stat-grid file-stats">
      <StatCard title="全部文件" value={files.length} note="此作品及其共享来源记录" />
      <StatCard title="图像" value={files.filter((item) => /\.(png|jpe?g|webp|svg)$/i.test(item.name)).length} note="三视图、参考图与过程截图" />
      <StatCard title="视频" value={files.filter((item) => /\.(mp4|mov)$/i.test(item.name)).length} note="本地镜头与成片文件" />
      <StatCard title="本地 Git" value={board.git?.enabled ? board.git.branch || '已启用' : '待初始化'} note={board.git?.head ? `构建时版本 ${board.git.head}` : '文件名版本与 Git 历史并用'} />
    </div>
    <Card className="section-card" title={`文件清单 · ${filtered.length}`} extra={<Input aria-label="搜索文件" className="file-search" placeholder="搜索文件名或路径" allowClear value={query} onChange={(event) => setQuery(event.target.value)} />}>
      <Table size="small" columns={columns} dataSource={filtered} rowKey="path" pagination={{ pageSize: 15, showSizeChanger: false }} scroll={{ x: 1000 }} locale={{ emptyText: <Empty description="没有匹配的文件" /> }} />
    </Card>
    <Card className="section-card" title="本地版本记录" extra={<Text type="secondary">构建看板时的 Git 快照</Text>}>
      {(board.git?.commits || []).length ? <div className="git-history">{board.git.commits.map((commit) => <div className="git-history-row" key={commit.hash}><code>{commit.hash}</code><strong>{commit.subject}</strong><span>{commit.date.replace('T', ' ').slice(0, 16)}</span></div>)}</div> : <Empty description="尚无本地提交记录" />}
    </Card>
  </>;
}

function AssetLibrary({ project, openDocument }) {
  const items = project.asset_items || [];
  const active = items.filter((item) => !item.historical);
  const columns = [
    { title: '预览', key: 'image', width: 86, render: (_, item) => <AssetImage asset={item} /> },
    { title: '资产', key: 'asset', width: 300, render: (_, item) => <div className="asset-description"><strong>{item.id} · {item.name}</strong><Text type="secondary">{item.image_name || '未登记文件名'}</Text></div> },
    { title: '类型', dataIndex: 'category', key: 'category', width: 100, filters: [...new Set(items.map((item) => item.category))].map((value) => ({ text: value, value })), onFilter: (value, item) => item.category === value },
    { title: '使用镜头', key: 'shots', width: 160, render: (_, item) => item.historical ? <Tag color="default">历史 / 暂不使用</Tag> : item.shots },
    { title: '状态', dataIndex: 'status', key: 'status', width: 250 },
    { title: '记录', key: 'file', width: 110, render: (_, item) => item.prompt_file ? <Button type="link" onClick={() => openDocument(item.prompt_file)}>资产提示词</Button> : '—' },
  ];
  return <>
    <SectionHeading eyebrow="ASSET LIBRARY" title="素材资产" description="人物、场景、道具的参考图与三视图记录；历史资产单独标记。" />
    {project.kind === 'archive' && <Alert className="page-alert" type="info" showIcon title="历史样片尚未登记完整资产矩阵" description="这里仅列出分镜方案中记录的角色参考。没有本地图片的条目会保留原始文件名，不会伪装成已备三视图。" />}
    <div className="stat-grid asset-stats">
      <StatCard title="全部登记" value={items.length} note="以项目资产矩阵为准" />
      <StatCard title="当前使用" value={active.length} note="不含历史 / 暂不使用" />
      <StatCard title="有本地预览" value={items.filter((item) => item.image).length} note="点击缩略图可查看" />
      <StatCard title="资产提示词" value={items.filter((item) => item.prompt_file).length} note="可打开源记录" />
    </div>
    <Card title="资产清单" className="section-card" extra={project.kind === 'project' && <Button type="link" onClick={() => openDocument('assets/asset-matrix.md')}>查看资产矩阵</Button>}>
      <Table columns={columns} dataSource={items} rowKey={(item) => `${item.id}:${item.image_name}`} size="small" pagination={{ pageSize: 12, showSizeChanger: false }} scroll={{ x: 1030 }} locale={{ emptyText: <Empty description="尚未登记资产" /> }} />
    </Card>
  </>;
}

function ShotMaterials({ project, goToPrompt }) {
  const assetMap = Object.fromEntries((project.asset_items || []).map((item) => [item.id, item]));
  const prompts = project.shot_prompts || [];
  const columns = [
    { title: '镜头', key: 'shot', width: 225, render: (_, shot) => <div className="asset-description"><strong>{String(shot.number).padStart(2, '0')} · {shot.title}</strong><Text type="secondary">{project.shots.find((item) => item.number === shot.number)?.verdict || '未登记审片结论'}</Text></div> },
    { title: '分镜计划使用', key: 'planned', width: 340, render: (_, shot) => <div className="chip-list">{shot.planned_asset_ids.length ? shot.planned_asset_ids.map((id) => assetMap[id] ? <AssetChip key={id} asset={assetMap[id]} /> : <Tag key={id}>{id}</Tag>) : '未登记'}</div> },
    { title: '当前提示词引用', key: 'actual', width: 340, render: (_, shot) => <div className="chip-list">{shot.reference_details?.length ? shot.reference_details.map((reference, index) => <ReferenceChip key={`${reference.name}-${index}`} reference={reference} assetMap={assetMap} />) : '未登记'}</div> },
    { title: '操作', key: 'action', width: 110, render: (_, shot) => <Button type="link" onClick={() => goToPrompt(shot.number)}>查看提示词</Button> },
  ];
  return <>
    <SectionHeading eyebrow="SHOT MATERIALS" title="分镜用料" description="逐镜对照资产矩阵计划与当前提示词实际引用的参考图。" />
    <Card title={`全部 ${prompts.length} 镜`} className="section-card" extra={<Text type="secondary">点击缩略图查看大图</Text>}>
      <Table columns={columns} dataSource={prompts} rowKey="number" size="small" pagination={{ pageSize: 8, showSizeChanger: false }} scroll={{ x: 1020 }} locale={{ emptyText: <Empty description="尚未登记逐镜用料" /> }} />
    </Card>
  </>;
}

function PromptLibrary({ project, initialShot, openDocument }) {
  const prompts = project.shot_prompts || [];
  const [number, setNumber] = useState(initialShot || prompts[0]?.number);
  useEffect(() => setNumber(initialShot || prompts[0]?.number), [project.path, initialShot]);
  const shot = prompts.find((item) => item.number === number) || prompts[0];
  const assetMap = Object.fromEntries((project.asset_items || []).map((item) => [item.id, item]));
  return <>
    <SectionHeading eyebrow="PROMPT LIBRARY" title="逐镜提示词" description="显示已登记的完整生成指令和参考图片；切换镜号查看每段。" />
    {prompts.length ? <>
      <Card className="section-card" title="选择分镜" extra={<Text type="secondary">{prompts.length} 镜已登记</Text>}>
        <Select aria-label="选择分镜" className="shot-switch" value={shot.number} options={prompts.map((item) => ({ value: item.number, label: `${String(item.number).padStart(2, '0')} · ${item.title}` }))} onChange={setNumber} showSearch={{ optionFilterProp: 'label' }} />
      </Card>
      <Card className="section-card" title={`${String(shot.number).padStart(2, '0')} · ${shot.title}`} extra={project.kind === 'project' ? <Button type="link" onClick={() => openDocument('prompts/shot-prompts.md')}>阅读提示词源文件</Button> : project.prompt_source ? <Button type="link" onClick={() => openDocument(project.prompt_source)}>阅读分镜方案</Button> : null}>
        <div className="prompt-label">生成提示词</div>
        <div className="prompt-text">{shot.text || '没有记录提示词正文'}</div>
        <div className="prompt-label prompt-reference-heading">参考图片</div>
        <div className="reference-grid">{(shot.reference_details || []).map((reference, index) => {
          const asset = assetMap[reference.asset_id];
          return <div className="reference-item" key={`${reference.name}-${index}`}><AssetImage asset={{ ...asset, image: reference.image, name: reference.name, id: reference.asset_id || '—' }} size={110} /><strong>{reference.asset_id || '未匹配资产'}</strong><Text type="secondary">{reference.name}</Text></div>;
        })}</div>
        {!shot.references.length && <Empty description="未登记参考图片" />}
      </Card>
    </> : <Empty description="尚未登记分镜提示词" />}
  </>;
}

function ProjectNavigator({ selected, onSelect }) {
  const [expanded, setExpanded] = useState(false);
  const [query, setQuery] = useState('');
  const matches = (project) => project.title.toLocaleLowerCase().includes(query.trim().toLocaleLowerCase());
  const groups = [
    { label: '当前项目', items: currentProjects.filter(matches) },
    { label: '历史样片', items: archiveProjects.filter(matches) },
  ];
  function choose(path) {
    onSelect(path);
    setExpanded(false);
    setQuery('');
  }
  return <nav className="project-nav" aria-label="二级作品导航">
    <div className="project-nav-bar">
      <div className="project-nav-identity">
        <span className="project-nav-kicker">作品导航 / {selected ? '当前作品' : '全部作品'}</span>
        <strong>{selected?.title || `全部 ${projects.length} 部作品`}</strong>
        {selected && <span className="project-nav-stage">{selected.stage}</span>}
      </div>
      <div className="project-nav-actions">
        {selected && <Button onClick={() => choose(null)}>全部作品</Button>}
        <Button type="primary" size="large" aria-expanded={expanded} onClick={() => setExpanded((value) => !value)}>{expanded ? '收起作品导航' : `浏览 / 切换作品 · ${projects.length}`}</Button>
      </div>
    </div>
    {expanded && <div className="project-nav-panel">
      <div className="project-nav-tools"><Input aria-label="在作品导航中搜索" placeholder="搜索作品名称" allowClear value={query} onChange={(event) => setQuery(event.target.value)} /><span>按作品选择，左侧菜单查看具体内容</span></div>
      <div className="project-nav-list">
        {groups.map((group) => group.items.length > 0 && <section key={group.label} className="project-nav-group"><h3>{group.label} · {group.items.length}</h3><div className="project-nav-grid">{group.items.map((project) => <button type="button" key={project.path} className={`project-nav-card${selected?.path === project.path ? ' is-current' : ''}`} onClick={() => choose(project.path)}><strong>{project.title}</strong><span>{project.stage}</span></button>)}</div></section>)}
        {groups.every((group) => !group.items.length) && <Empty description="没有匹配的作品" />}
      </div>
    </div>}
  </nav>;
}

function App() {
  const [mobile, setMobile] = useState(() => window.matchMedia('(max-width: 767px)').matches);
  const [menuOpen, setMenuOpen] = useState(false);
  const [route, setRoute] = useState(routeFromHash);
  const [promptShot, setPromptShot] = useState(null);
  const [lastProjectPath, setLastProjectPath] = useState(() => routeFromHash().path || currentProjects[0]?.path || projects[0]?.path || null);
  useEffect(() => {
    const update = () => {
      const next = routeFromHash();
      setRoute(next);
      if (next.path) setLastProjectPath(next.path);
    };
    window.addEventListener('hashchange', update);
    return () => window.removeEventListener('hashchange', update);
  }, []);
  const selected = route.path ? getProject(route.path) : null;
  function navigate(path, view = 'progress', doc = null) {
    setMenuOpen(false);
    window.location.hash = path ? `project=${encodeURIComponent(path)}&view=${view}${doc ? `&doc=${encodeURIComponent(doc)}` : ''}` : 'overview';
    setRoute({ path: path || null, view, doc });
    if (path) setLastProjectPath(path);
    if (view !== 'prompts') setPromptShot(null);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }
  function goToPrompt(number) { if (selected) { setPromptShot(number); navigate(selected.path, 'prompts'); } }
  function openDocument(value) {
    const item = findDocument(selected, value);
    if (item) navigate(selected.path, 'documents', item.key);
  }
  const goToProject = (path) => navigate(path);
  const recentProject = getProject(lastProjectPath);
  const sectionItems = Object.entries(viewLabels).map(([key, label]) => ({
    key: `view:${key}`,
    icon: key === 'progress' ? <DashboardOutlined /> : key === 'assets' ? <AppstoreOutlined /> : key === 'files' ? <FolderOpenOutlined /> : <FileTextOutlined />,
    label,
    disabled: !recentProject,
  }));
  return (
    <ConfigProvider
      locale={zhCN}
      theme={{
        token: {
          colorPrimary: '#1677ff',
          colorBgLayout: '#f5f7fb',
          colorBgContainer: '#ffffff',
          borderRadius: 8,
          fontFamily: '-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif',
        },
        components: {
          Layout: { headerBg: '#ffffff', headerHeight: 64, headerPadding: '0 28px' },
        },
      }}
    >
      <Layout className="workspace-layout">
        <Sider width={248} breakpoint="md" collapsedWidth={0} collapsed={mobile && !menuOpen} trigger={null} onBreakpoint={(broken) => { setMobile(broken); setMenuOpen(false); }} className="workspace-sider">
          <div hidden={mobile && !menuOpen}>
          <div className="brand"><span className="brand-mark">TS</span><div><strong>Thirdspace AIGC</strong><small>制作管理台</small></div></div>
          <div className="sider-scroll">
            <Menu theme="dark" mode="inline" selectedKeys={selected ? [] : ['overview']} items={[{ key: 'overview', icon: <DashboardOutlined />, label: '作品总览' }]} onClick={() => goToProject(null)} />
            <div className="sider-heading">作品工作区</div>
            <Menu theme="dark" mode="inline" selectedKeys={selected ? [`view:${route.view}`] : []} items={sectionItems} onClick={({ key }) => navigate(selected?.path || lastProjectPath, key.slice(5))} />
            <div className="sider-context"><small>{selected ? '当前作品' : '最近查看'}</small><strong>{recentProject?.title || '请先选择作品'}</strong><span>在主导航下方的作品导航区切换</span></div>
          </div>
          </div>
        </Sider>
        {mobile && menuOpen && <button className="sidebar-dismiss" aria-label="关闭导航菜单" onClick={() => setMenuOpen(false)} />}
        <Layout className="workspace-main">
          <Header className="app-header">
            {mobile && <Button icon={<MenuOutlined />} aria-label="导航菜单" aria-expanded={menuOpen} onClick={() => setMenuOpen(!menuOpen)} />}
            <Breadcrumb items={[{ title: 'Thirdspace AIGC' }, { title: selected ? selected.title : '作品总览' }, ...(selected ? [{ title: viewLabels[route.view] }] : [])]} />
            <Tag>数据快照 · 刷新页面查看最新记录</Tag>
          </Header>
          <ProjectNavigator selected={selected} onSelect={(path) => navigate(path, path && selected ? route.view : 'progress')} />
          <Content>
            <main className="page-content">
              {selected ? (
                <>
                  <ProjectHeading project={selected} goToOverview={() => goToProject(null)} />
                  {route.view === 'documents' ? <DocumentLibrary project={selected} initialDoc={route.doc} openDocument={openDocument} /> : route.view === 'assets' ? <AssetLibrary project={selected} openDocument={openDocument} /> : route.view === 'materials' ? <ShotMaterials project={selected} goToPrompt={goToPrompt} /> : route.view === 'prompts' ? <PromptLibrary project={selected} initialShot={promptShot} openDocument={openDocument} /> : route.view === 'files' ? <FileRegistry project={selected} openDocument={openDocument} /> : selected.kind === 'archive' ? <ArchiveProject project={selected} openDocument={openDocument} /> : <ActiveProject project={selected} goToProject={goToProject} openDocument={openDocument} />}
                </>
              ) : <Overview goToProject={goToProject} />}
              <footer className="page-footer">数据生成于 {board.updated.replace('T', ' ')} · {board.timezone} · <Button type="link" onClick={() => navigate(selected?.path || lastProjectPath, 'documents', 'queue/README.md')}>队列说明</Button></footer>
            </main>
          </Content>
        </Layout>
      </Layout>
    </ConfigProvider>
  );
}

createRoot(document.getElementById('root')).render(<App />);
