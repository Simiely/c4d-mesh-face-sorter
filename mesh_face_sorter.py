"""C4D Mesh Face Sorter

按面数/顶点数/存储大小排列场景中所有网格体，快速定位高面数模型、
批量减面、孤立显示、删除空网格、导出场景报表。

Based on: https://github.com/Simiely/blender-mesh-face-sorter
Compatible: C4D 2023+ (2024/2025/2026)
License: MIT
"""

import c4d
import datetime
from c4d import gui

# ──────────────────────────────────────────────
# Plugin metadata
# ──────────────────────────────────────────────
PLUGIN_ID = 1052327
PLUGIN_NAME = "Mesh Face Sorter"
PLUGIN_HELP = "按面数/顶点数/存储大小排列网格体"

# ──────────────────────────────────────────────
# Gadget IDs
# ──────────────────────────────────────────────
# Status area
GID_STATUS_GROUP = 1000
GID_STATUS_LABEL = 1001
GID_PROGRESSBAR = 1002

# Stats area
GID_STATS_GROUP = 1010
GID_STATS_COUNT = 1011
GID_STATS_FACES = 1012
GID_STATS_VERTS = 1013
GID_STATS_SIZE = 1014
GID_HINT_LABEL = 1015

# Sort controls
GID_SORT_GROUP = 1020
GID_SORT_COMBO = 1021
GID_SORT_TOGGLE = 1022

# Action buttons
GID_BTN_REFRESH = 1030
GID_BTN_SELECT_ALL = 1031
GID_BTN_SHOW_ALL = 1032
GID_BTN_DELETE_EMPTY = 1033
GID_BTN_PURGE = 1034
GID_BTN_EXPORT = 1035

# Decimate controls
GID_DECIMATE_GROUP = 1040
GID_DECIMATE_RATIO = 1041
GID_BTN_DECIMATE_BATCH = 1042
GID_BTN_DECIMATE_APPLY = 1043

# List area (header + scroll)
GID_LIST_HEADER = 1050
GID_LIST_SCROLL = 1051
GID_LIST_GROUP = 1052  # parent inside scroll, rows attached here

# Dynamic list rows start from here
GID_LIST_ROW_BASE = 2000
GID_LIST_ROW_MAX = 20000  # upper bound for dynamic IDs

# Sub-control offset for each list row
OFFSET_BTN_SELECT = 0
OFFSET_BTN_ISOLATE = 1
OFFSET_BTN_DECIMATE = 2

# ──────────────────────────────────────────────
# Cache
# ──────────────────────────────────────────────
class _Cache:
    """缓存层：避免每次打开面板或切换排序时重新扫描场景。
    纯手动刷新模式：只有点击「刷新」或加载新文件后才重新扫描。
    """
    stats = None

    @classmethod
    def invalidate(cls):
        cls.stats = None

    @classmethod
    def has_data(cls):
        return cls.stats is not None

    @classmethod
    def store(cls, stats):
        cls.stats = stats


# ──────────────────────────────────────────────
# Scan status (used by dialog Timer)
# ──────────────────────────────────────────────
class _ScanStatus:
    is_scanning = False
    current = 0
    total = 0
    percent = 0
    message = ""
    last_scanned_count = 0
    last_scan_time = ""

    @classmethod
    def reset(cls, total):
        cls.is_scanning = True
        cls.current = 0
        cls.total = total
        cls.percent = 0
        cls.message = "扫描中..."

    @classmethod
    def update(cls, current):
        cls.current = current
        if cls.total > 0:
            cls.percent = int(current * 100 / cls.total)
            cls.message = f"扫描中... {current}/{cls.total} ({cls.percent}%)"

    @classmethod
    def finish(cls, count):
        cls.is_scanning = False
        cls.current = cls.total
        cls.percent = 100
        cls.last_scanned_count = count
        cls.last_scan_time = datetime.datetime.now().strftime("%H:%M:%S")
        cls.message = f"扫描完成：{count} 个网格体（{cls.last_scan_time}）"

    @classmethod
    def idle(cls):
        cls.message = "未扫描，请点击「刷新列表」"

    @classmethod
    def get_face_count_str(cls, stats):
        total_faces = sum(s["faces"] for s in stats) if stats else 0
        return format_number(total_faces)

    @classmethod
    def get_vert_count_str(cls, stats):
        total_verts = sum(s["vertices"] for s in stats) if stats else 0
        return format_number(total_verts)

    @classmethod
    def get_size_str(cls, stats):
        total_size = sum(s["size"] for s in stats) if stats else 0
        return format_size(total_size)


_ScanStatus.idle()


# ──────────────────────────────────────────────
# Sort key mapping
# ──────────────────────────────────────────────
_SORT_KEY_MAP = {
    "FACES": "faces",
    "VERTS": "vertices",
    "SIZE": "size",
}

_SORT_LABELS = {
    "FACES": "面数",
    "VERTS": "顶点数",
    "SIZE": "存储大小",
}

# ──────────────────────────────────────────────
# Helper: collect all scene objects recursively
# ──────────────────────────────────────────────
def _collect_all_objects(doc):
    """递归收集场景中所有物体（含子级）"""
    result = []
    def _walk(obj):
        if obj is None:
            return
        result.append(obj)
        child = obj.GetDown()
        while child:
            _walk(child)
            child = child.GetNext()
    for obj in doc.GetObjects():
        _walk(obj)
    return result


# ──────────────────────────────────────────────
# Helper: estimate mesh memory size
# ──────────────────────────────────────────────
def _estimate_mesh_size(poly_obj):
    """估算网格体内存占用（字节），用于相对比较。
    
    基于点、多边形、UVW标签、顶点色标签等数据量估算。
    C4D 没有直接的内存占用 API，此值为相对参考。
    """
    size = 0
    # 点：位置(12B) + 法线(12B) ≈ 24B
    point_count = poly_obj.GetPointCount()
    size += point_count * 24

    # 多边形：每个多边形约 16B (4个顶点索引)
    poly_count = poly_obj.GetPolygonCount()
    size += poly_count * 16

    # UVW 标签
    uvw_tag = poly_obj.GetTag(c4d.Tuvw)
    if uvw_tag:
        try:
            data = uvw_tag.GetSlow()
            size += len(data) * 8 if data else 0
        except Exception:
            pass

    # 顶点色标签
    vc_tag = poly_obj.GetTag(c4d.Tvertexcolor)
    if vc_tag:
        try:
            data = vc_tag.GetDataAddressW()
            size += poly_count * 4 * 16  # RGBA per vertex
        except Exception:
            pass

    return size


# ──────────────────────────────────────────────
# Helper: format numbers
# ──────────────────────────────────────────────
def format_number(n):
    if n >= 1000000:
        return f"{n / 1000000:.1f}M"
    if n >= 1000:
        return f"{n / 1000:.1f}K"
    return str(n)


def format_size(n):
    if n >= 1024 * 1024 * 1024:
        return f"{n / (1024**3):.1f} GB"
    if n >= 1024 * 1024:
        return f"{n / (1024**2):.1f} MB"
    if n >= 1024:
        return f"{n / 1024:.1f} KB"
    return f"{n} B"


# ──────────────────────────────────────────────
# Helper: scan meshes
# ──────────────────────────────────────────────
def _scan_meshes(doc, with_progress=False):
    """扫描场景中所有多边形物体，收集统计信息。"""
    all_objects = _collect_all_objects(doc)
    total = len(all_objects)

    if with_progress:
        _ScanStatus.reset(total)

    stats = []
    for i, obj in enumerate(all_objects, 1):
        if obj.IsInstanceOf(c4d.Opolygon):
            poly_count = obj.GetPolygonCount()
            point_count = obj.GetPointCount()
            # Check visibility / selection state
            is_hidden = obj.GetBit(c4d.BIT_HIDDEN)
            is_selected = obj.GetBit(c4d.BIT_ACTIVE)
            stats.append({
                "object": obj,
                "name": obj.GetName(),
                "faces": poly_count,
                "vertices": point_count,
                "size": _estimate_mesh_size(obj),
                "selected": is_selected,
                "hidden": is_hidden,
            })
        if with_progress:
            _ScanStatus.update(i)

    if with_progress:
        _ScanStatus.finish(len(stats))
    return stats


def collect_mesh_stats(doc, sort_by="FACES", descending=True, force=False):
    """获取排序后的网格体统计信息。
    
    force=True: 重新扫描（点击「刷新」时）
    缓存为空: 自动扫描（首次打开）
    缓存有效: 直接重排（切换排序方式时）
    """
    if force or not _Cache.has_data():
        stats = _scan_meshes(doc, with_progress=force)
        _Cache.store(stats)
    else:
        stats = _Cache.stats

    sorted_stats = sorted(
        stats,
        key=lambda x: x[_SORT_KEY_MAP[sort_by]],
        reverse=descending,
    )
    return sorted_stats


# ──────────────────────────────────────────────
# Polygon Reduction helpers
# ──────────────────────────────────────────────
DECIMATE_TAG_NAME = "MeshFaceSorter_Reduction"

def add_decimate_tag(obj, ratio=0.5):
    """给多边形物体添加 Polygon Reduction Tag。
    
    ratio: 保留比例 (0.01~1.0)，内部换算为 C4D 的 strength。
    C4D strength = 1.0 - ratio（C4D 的 strength 是减少强度）。
    
    返回: (是否新创建, tag对象)
    """
    if not obj.IsInstanceOf(c4d.Opolygon):
        return False, None

    # 检查是否已有同名 Tag
    tag = obj.GetTag(c4d.Tpolyredux)
    if tag:
        # 更新已有 Tag 的强度
        strength = 1.0 - ratio
        tag[c4d.POLYREDUXTAG_STRENGTH] = max(0.0, min(1.0, strength))
        return False, tag

    # 创建新 Tag
    tag = obj.MakeTag(c4d.Tpolyredux)
    if tag is None:
        return False, None

    tag.SetName(DECIMATE_TAG_NAME)
    strength = 1.0 - ratio
    tag[c4d.POLYREDUXTAG_STRENGTH] = max(0.0, min(1.0, strength))
    tag[c4d.POLYREDUXTAG_PRESERVE_3D_BOUNDARY] = True
    tag[c4d.POLYREDUXTAG_PRESERVE_UV_BOUNDARY] = True
    return True, tag


def apply_decimate(obj):
    """应用物体的 Polygon Reduction，直接减面。
    
    使用 c4d.utils.PolygonReduction 直接修改几何体，
    然后移除对应的 Tag。
    
    返回: bool
    """
    if not obj.IsInstanceOf(c4d.Opolygon):
        return False

    tag = obj.GetTag(c4d.Tpolyredux)
    if tag is None:
        return False

    try:
        strength = tag[c4d.POLYREDUXTAG_STRENGTH]
    except Exception:
        return False

    poly_reduction = c4d.utils.PolygonReduction()
    if poly_reduction is None:
        return False

    settings = c4d.BaseContainer()
    try:
        settings[c4d.POLYREDUXOBJECT_PRESERVE_3D_BOUNDARY] = bool(
            tag[c4d.POLYREDUXTAG_PRESERVE_3D_BOUNDARY]
        )
    except Exception:
        settings[c4d.POLYREDUXOBJECT_PRESERVE_3D_BOUNDARY] = True
    try:
        settings[c4d.POLYREDUXOBJECT_PRESERVE_UV_BOUNDARY] = bool(
            tag[c4d.POLYREDUXTAG_PRESERVE_UV_BOUNDARY]
        )
    except Exception:
        settings[c4d.POLYREDUXOBJECT_PRESERVE_UV_BOUNDARY] = True

    doc = c4d.documents.GetActiveDocument()

    data = {
        "_op": obj,
        "_doc": doc,
        "_settings": settings,
        "_thread": None,
    }

    if not poly_reduction.PreProcess(data):
        return False

    poly_reduction.SetReductionStrengthLevel(strength)
    obj.Message(c4d.MSG_UPDATE)

    # 移除 Tag
    tag.Remove()
    return True


# ──────────────────────────────────────────────
# Dialog — Main UI
# ──────────────────────────────────────────────
class MeshSorterDialog(gui.GeDialog):
    """主面板对话框"""

    def __init__(self):
        super().__init__()
        self.doc = None
        self.sort_by = "FACES"
        self.descending = True
        self.decimate_ratio = 0.5

    def _get_active_doc(self):
        """获取当前活动文档"""
        doc = c4d.documents.GetActiveDocument()
        if doc is None:
            doc = self.doc
        self.doc = doc
        return doc

    # ── Layout ──────────────────────────────────
    def CreateLayout(self):
        """构建对话框布局"""
        self.SetTitle("网格排序器 Mesh Face Sorter")

        # ── 状态区 ──
        self.GroupBegin(GID_STATUS_GROUP, c4d.BFH_SCALEFIT, 1, 0, name="")
        self.GroupBorderSpace(5, 2, 5, 2)
        self.AddStaticText(GID_STATUS_LABEL, c4d.BFH_SCALEFIT, 0, 0, name=_ScanStatus.message, borderstyle=c4d.BORDER_NONE)
        self.AddProgressBar(GID_PROGRESSBAR, c4d.BFH_SCALEFIT, 300, 8)
        self.Enable(GID_PROGRESSBAR, False)
        self.GroupEnd()

        # ── 提示区（手动刷新模式） ──
        self.AddStaticText(GID_HINT_LABEL, c4d.BFH_SCALEFIT, 0, 0,
                           name="手動刷新模式：增删物体后请点「刷新列表」",
                           borderstyle=c4d.BORDER_NONE)

        # ── 统计区 ──
        self.GroupBegin(GID_STATS_GROUP, c4d.BFH_SCALEFIT, 4, 0, name="")
        self.GroupBorderSpace(5, 2, 5, 2)
        self.AddStaticText(GID_STATS_COUNT, c4d.BFH_SCALEFIT, 0, 0, name="网格体: 0")
        self.AddStaticText(GID_STATS_FACES, c4d.BFH_SCALEFIT, 0, 0, name="面数: 0")
        self.AddStaticText(GID_STATS_VERTS, c4d.BFH_SCALEFIT, 0, 0, name="顶点: 0")
        self.AddStaticText(GID_STATS_SIZE, c4d.BFH_SCALEFIT, 0, 0, name="存储: 0 B")
        self.GroupEnd()

        # ── 排序区 ──
        self.GroupBegin(GID_SORT_GROUP, c4d.BFH_SCALEFIT, 3, 0, name="排序：")
        self.GroupBorderSpace(5, 2, 5, 2)
        self.AddComboBox(GID_SORT_COMBO, c4d.BFH_SCALEFIT, 120, 12)
        self.AddChild(GID_SORT_COMBO, 0, "面数")
        self.AddChild(GID_SORT_COMBO, 1, "顶点数")
        self.AddChild(GID_SORT_COMBO, 2, "存储大小")
        self.SetInt32(GID_SORT_COMBO, 0)
        # Toggle button for ascending/descending
        self.AddButton(GID_SORT_TOGGLE, c4d.BFH_SCALEFIT, 30, 20, name="↓↑")
        self.GroupEnd()

        # ── 操作按钮区 ──
        # Row 1
        self.AddButton(GID_BTN_REFRESH, c4d.BFH_SCALEFIT, 120, 20, name="刷新列表")
        self.AddButton(GID_BTN_SELECT_ALL, c4d.BFH_SCALEFIT, 120, 20, name="选中所有网格体")

        # Row 2
        self.AddButton(GID_BTN_SHOW_ALL, c4d.BFH_SCALEFIT, 100, 20, name="显示全部")
        self.AddButton(GID_BTN_DELETE_EMPTY, c4d.BFH_SCALEFIT, 100, 20, name="删除无面")
        self.AddButton(GID_BTN_PURGE, c4d.BFH_SCALEFIT, 100, 20, name="清理数据")

        # Row 3
        self.AddButton(GID_BTN_EXPORT, c4d.BFH_SCALEFIT, 140, 20, name="导出 md 报表")

        # ── 减面区 ──
        self.GroupBegin(GID_DECIMATE_GROUP, c4d.BFH_SCALEFIT, 3, 0, name="保留比例：")
        self.GroupBorderSpace(5, 2, 5, 2)
        self.AddEditFloatArrows(GID_DECIMATE_RATIO, c4d.BFH_SCALEFIT, 80, 10, step=0.05, min=0.01, max=1.0)
        self.SetFloat(GID_DECIMATE_RATIO, 0.5)
        self.AddButton(GID_BTN_DECIMATE_BATCH, c4d.BFH_SCALEFIT, 120, 20, name="减面 Tag")
        self.AddButton(GID_BTN_DECIMATE_APPLY, c4d.BFH_SCALEFIT, 120, 20, name="应用减面")
        self.GroupEnd()

        # ── 列表区 ──
        self.AddStaticText(GID_LIST_HEADER, c4d.BFH_SCALEFIT, 0, 0,
                           name="  物体名称                                       面数*       ",
                           borderstyle=c4d.BORDER_THIN_IN)
        # Scroll group for list rows
        self.ScrollGroupBegin(GID_LIST_SCROLL, c4d.BFH_SCALEFIT | c4d.BFV_SCALEFIT, 400, 300)
        self.GroupBegin(GID_LIST_GROUP, c4d.BFH_SCALEFIT | c4d.BFV_SCALEFIT, 1, 0)
        self.GroupEnd()
        self.ScrollGroupEnd()

        # ── 定时器（每 1 秒刷新一次面板） ──
        self.SetTimer(1000)

        return True

    # ── Timer ───────────────────────────────────
    def Timer(self, msg):
        """定时刷新面板状态和列表"""
        if _ScanStatus.is_scanning:
            self._update_status()
            self._update_progress()
            c4d.EventAdd()
        else:
            # 非扫描状态，定期刷新实时状态（选中、隐藏变化）
            if _Cache.has_data() and self.doc is not None:
                self._refresh_list(self.doc)
        self.SetTimer(1000)

    # ── Command Handler ─────────────────────────
    def Command(self, gid, msg):
        """处理按钮点击和控件变化"""
        doc = self._get_active_doc()
        if doc is None:
            return True

        # ── Sort combo ──
        if gid == GID_SORT_COMBO:
            sort_idx = self.GetInt32(GID_SORT_COMBO)
            mapping = {0: "FACES", 1: "VERTS", 2: "SIZE"}
            self.sort_by = mapping.get(sort_idx, "FACES")
            self._refresh_list(doc)

        # ── Sort toggle ──
        elif gid == GID_SORT_TOGGLE:
            self.descending = not self.descending
            self._refresh_list(doc)

        # ── Decimate ratio ──
        elif gid == GID_DECIMATE_RATIO:
            self.decimate_ratio = self.GetFloat(GID_DECIMATE_RATIO)

        # ── Refresh ──
        elif gid == GID_BTN_REFRESH:
            self._do_scan(doc)

        # ── Select all ──
        elif gid == GID_BTN_SELECT_ALL:
            self._do_select_all(doc)

        # ── Show all ──
        elif gid == GID_BTN_SHOW_ALL:
            self._do_show_all(doc)

        # ── Delete empty ──
        elif gid == GID_BTN_DELETE_EMPTY:
            self._do_delete_empty(doc)

        # ── Purge orphan data ──
        elif gid == GID_BTN_PURGE:
            self._do_purge(doc)

        # ── Export MD report ──
        elif gid == GID_BTN_EXPORT:
            self._do_export(doc)

        # ── Batch decimate ──
        elif gid == GID_BTN_DECIMATE_BATCH:
            self._do_decimate_batch(doc)

        # ── Apply decimate ──
        elif gid == GID_BTN_DECIMATE_APPLY:
            self._do_decimate_apply(doc)

        # ── Dynamic row buttons ──
        elif GID_LIST_ROW_BASE <= gid < GID_LIST_ROW_MAX:
            self._handle_list_row_action(gid, doc)

        return True

    # ── Core Actions ────────────────────────────

    def _do_scan(self, doc):
        """执行扫描"""
        _Cache.invalidate()
        stats = collect_mesh_stats(doc, sort_by=self.sort_by,
                                   descending=self.descending, force=True)
        # collect_mesh_stats 已自动存储缓存
        self._update_status()
        self._update_stats(stats)
        self._build_list(stats)

    def _do_select_all(self, doc):
        """选中所有多边形物体"""
        doc.StartUndo()
        # 取消全部选中
        for obj in _collect_all_objects(doc):
            if obj.IsInstanceOf(c4d.Opolygon):
                doc.AddUndo(c4d.UNDOTYPE_CHANGE_SMALL, obj)
                obj.DelBit(c4d.BIT_ACTIVE)
        # 选中所有多边形物体
        for obj in _collect_all_objects(doc):
            if obj.IsInstanceOf(c4d.Opolygon):
                doc.AddUndo(c4d.UNDOTYPE_CHANGE_SMALL, obj)
                obj.SetBit(c4d.BIT_ACTIVE)
        doc.EndUndo()
        c4d.EventAdd()
        self._refresh_list(doc)

    def _do_show_all(self, doc):
        """取消所有物体的隐藏"""
        doc.StartUndo()
        count = 0
        for obj in _collect_all_objects(doc):
            if obj.GetBit(c4d.BIT_HIDDEN):
                doc.AddUndo(c4d.UNDOTYPE_CHANGE_SMALL, obj)
                obj.DelBit(c4d.BIT_HIDDEN)
                count += 1
        doc.EndUndo()
        _Cache.invalidate()
        c4d.EventAdd()
        self._refresh_list(doc)

    def _do_delete_empty(self, doc):
        """删除面数为 0 的空网格体"""
        empty_objs = [
            obj for obj in _collect_all_objects(doc)
            if obj.IsInstanceOf(c4d.Opolygon) and obj.GetPolygonCount() == 0
        ]
        if not empty_objs:
            gui.MessageDialog("场景中没有空网格体。")
            return

        count = len(empty_objs)
        result = gui.QuestionDialog(f"确定删除 {count} 个面数为 0 的空网格体吗？")
        if not result:
            return

        doc.StartUndo()
        for obj in empty_objs:
            doc.AddUndo(c4d.UNDOTYPE_DELETE, obj)
            obj.Remove()
        doc.EndUndo()
        _Cache.invalidate()
        c4d.EventAdd()
        self._refresh_list(doc)

    def _do_purge(self, doc):
        """清理未使用的材质/贴图等数据"""
        purged = 0
        doc.StartUndo()

        # 收集所有已使用的材质
        used_materials = set()
        for obj in _collect_all_objects(doc):
            if obj.IsInstanceOf(c4d.Opolygon):
                for tag in obj.GetTags():
                    if tag.GetType() == c4d.Ttexture:
                        mat = tag[c4d.TEXTURETAG_MATERIAL]
                        if mat:
                            used_materials.add(mat)

        # 收集所有已使用的着色器
        used_shaders = set()
        for mat in used_materials:
            for shader in mat.GetChildren():
                used_shaders.add(shader)

        # 收集所有已使用的位图
        used_bitmaps = set()
        for shader in used_shaders:
            if shader.GetType() == c4d.Xbitmap:
                bmp = shader[c4d.BITMAPSHADER_FILENAME]
                if bmp:
                    used_bitmaps.add(bmp)

        # 删除未使用的材质
        for mat in doc.GetMaterials():
            if mat not in used_materials:
                doc.AddUndo(c4d.UNDOTYPE_DELETE, mat)
                try:
                    mat.Remove()
                    purged += 1
                except Exception:
                    pass

        doc.EndUndo()
        _Cache.invalidate()
        c4d.EventAdd()
        gui.MessageDialog(f"已清理 {purged} 个未使用的材质。")

    def _do_export(self, doc):
        """导出 Markdown 报表"""
        stats = collect_mesh_stats(doc, sort_by=self.sort_by,
                                   descending=self.descending, force=True)
        if not stats:
            gui.MessageDialog("场景中没有网格体可导出。")
            return

        # 弹出保存对话框
        path = c4d.storage.SaveDialog(
            title="导出 MD 报表",
            flags=c4d.FILESELECT_SAVE,
            def_path="",
            def_file="mesh_report.md",
        )
        if path is None or path == "":
            return

        if not path.lower().endswith(".md"):
            path += ".md"

        total_faces = sum(s["faces"] for s in stats)
        total_verts = sum(s["vertices"] for s in stats)
        total_size = sum(s["size"] for s in stats)

        sort_label = _SORT_LABELS.get(self.sort_by, "面数")
        order_label = "降序" if self.descending else "升序"

        lines = [
            "# 网格体报表",
            "",
            f"- **生成时间**：{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"- **排序方式**：{sort_label}（{order_label}）",
            f"- **网格体总数**：{len(stats)}",
            f"- **总面数**：{total_faces}",
            f"- **总顶点**：{total_verts}",
            f"- **总存储**：{format_size(total_size)}",
            "",
            "| # | 物体名称 | 面数 | 顶点数 | 存储 | 选中 | 隐藏 |",
            "|---|---|---|---|---|---|---|",
        ]
        for i, s in enumerate(stats, 1):
            lines.append(
                f"| {i} | {s['name']} | {s['faces']} | {s['vertices']} "
                f"| {format_size(s['size'])} "
                f"| {'是' if s['selected'] else '否'} "
                f"| {'是' if s['hidden'] else '否'} |"
            )
        lines.append("")

        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write("\n".join(lines))
            gui.MessageDialog(f"已导出 {len(stats)} 个网格体到：\n{path}")
        except Exception as e:
            gui.MessageDialog(f"导出失败：{e}")

    def _do_decimate_batch(self, doc):
        """给选中的多边形物体批量添加减面 Tag"""
        selected = [obj for obj in _collect_all_objects(doc)
                    if obj.IsInstanceOf(c4d.Opolygon) and obj.GetBit(c4d.BIT_ACTIVE)]
        if not selected:
            gui.MessageDialog("请先至少选中一个网格体。")
            return

        ratio = self.decimate_ratio
        added = 0
        skipped = 0

        doc.StartUndo()
        for obj in selected:
            ok, _ = add_decimate_tag(obj, ratio)
            if ok:
                doc.AddUndo(c4d.UNDOTYPE_NEW, obj.GetTag(c4d.Tpolyredux))
                added += 1
            else:
                skipped += 1
        doc.EndUndo()

        c4d.EventAdd()
        msg = f"已添加减面 Tag：{added} 个物体"
        if skipped:
            msg += f"（跳过 {skipped} 个已有 Tag）"
        gui.MessageDialog(msg)

    def _do_decimate_apply(self, doc):
        """应用选中物体的减面 Tag"""
        selected = [obj for obj in _collect_all_objects(doc)
                    if obj.IsInstanceOf(c4d.Opolygon) and obj.GetBit(c4d.BIT_ACTIVE)]
        if not selected:
            gui.MessageDialog("请先至少选中一个网格体。")
            return

        applied = 0
        skipped = 0
        for obj in selected:
            tag = obj.GetTag(c4d.Tpolyredux)
            if tag is None:
                skipped += 1
                continue
            if apply_decimate(obj):
                applied += 1
            else:
                skipped += 1

        c4d.EventAdd()
        _Cache.invalidate()
        self._refresh_list(doc)

        msg = f"已应用 {applied} 个减面"
        if skipped:
            msg += f"（跳过 {skipped} 个无 Tag 或应用失败的物体）"
        gui.MessageDialog(msg)

    # ── List row actions ────────────────────────

    def _handle_list_row_action(self, gid, doc):
        """处理列表行中的按钮点击"""
        # 计算行索引和子按钮类型
        offset = gid - GID_LIST_ROW_BASE
        row_index = offset // 3
        action_type = offset % 3

        stats = _Cache.stats
        if stats is None or row_index >= len(stats):
            return

        try:
            entry = stats[row_index]
            obj = entry["object"]
        except Exception:
            return

        if action_type == OFFSET_BTN_SELECT:
            # 选中该物体
            doc.StartUndo()
            # 取消全部选中
            for o in _collect_all_objects(doc):
                if o.IsInstanceOf(c4d.Opolygon):
                    doc.AddUndo(c4d.UNDOTYPE_CHANGE_SMALL, o)
                    o.DelBit(c4d.BIT_ACTIVE)
            # 选中目标物体
            doc.AddUndo(c4d.UNDOTYPE_CHANGE_SMALL, obj)
            obj.SetBit(c4d.BIT_ACTIVE)
            doc.SetActiveObject(obj)
            doc.EndUndo()
            c4d.EventAdd()
            self._refresh_list(doc)

        elif action_type == OFFSET_BTN_ISOLATE:
            # 孤立显示
            doc.StartUndo()
            for o in _collect_all_objects(doc):
                if o.IsInstanceOf(c4d.Opolygon):
                    doc.AddUndo(c4d.UNDOTYPE_CHANGE_SMALL, o)
                    if o == obj:
                        o.DelBit(c4d.BIT_HIDDEN)
                    else:
                        o.SetBit(c4d.BIT_HIDDEN)
            doc.EndUndo()
            _Cache.invalidate()
            c4d.EventAdd()
            self._refresh_list(doc)

        elif action_type == OFFSET_BTN_DECIMATE:
            # 给该物体添加减面 Tag
            ratio = self.decimate_ratio
            doc.StartUndo()
            ok, tag = add_decimate_tag(obj, ratio)
            if ok and tag:
                doc.AddUndo(c4d.UNDOTYPE_NEW, tag)
            doc.EndUndo()
            c4d.EventAdd()

    # ── UI Update Helpers ───────────────────────

    def _update_status(self):
        """更新状态文本"""
        self.SetString(GID_STATUS_LABEL, _ScanStatus.message)

    def _update_progress(self):
        """更新进度条"""
        if _ScanStatus.total > 0:
            self.SetFloat(GID_PROGRESSBAR, _ScanStatus.percent / 100.0,
                          allowOutOfRange=True)
        self._update_status()

    def _update_stats(self, stats):
        """更新统计信息"""
        total_faces = sum(s["faces"] for s in stats)
        total_verts = sum(s["vertices"] for s in stats)
        total_size = sum(s["size"] for s in stats)
        self.SetString(GID_STATS_COUNT, f"网格体: {len(stats)}")
        self.SetString(GID_STATS_FACES, f"面数: {format_number(total_faces)}")
        self.SetString(GID_STATS_VERTS, f"顶点: {format_number(total_verts)}")
        self.SetString(GID_STATS_SIZE, f"存储: {format_size(total_size)}")

    def _refresh_list(self, doc):
        """重新排序并更新列表"""
        stats = collect_mesh_stats(doc, sort_by=self.sort_by,
                                   descending=self.descending)
        self._update_stats(stats)
        self._build_list(stats)

    def _build_list(self, stats):
        """构建列表行"""
        # 清空列表组
        self.LayoutFlushGroup(GID_LIST_GROUP)
        self.GroupBegin(GID_LIST_GROUP, c4d.BFH_SCALEFIT | c4d.BFV_SCALEFIT, 1, 1)

        if not stats:
            self.AddStaticText(0, c4d.BFH_SCALEFIT, 0, 0, name="  (场景中没有网格体)")
            self.GroupEnd()
            self.LayoutChanged(GID_LIST_GROUP)
            return

        MAX_DISPLAY = 500
        display_stats = stats[:MAX_DISPLAY]

        for idx, s in enumerate(display_stats):
            try:
                obj = s["object"]
                is_selected = obj.GetBit(c4d.BIT_ACTIVE)
                is_hidden = obj.GetBit(c4d.BIT_HIDDEN)
            except Exception:
                continue

            gid = GID_LIST_ROW_BASE + idx * 3
            row_group = gid + 1000  # unique group ID for this row

            # 每行用 Group 水平排列
            self.GroupBegin(row_group, c4d.BFH_SCALEFIT, 3, 1)

            # 名称按钮 + Select
            name_text = s["name"]
            if len(name_text) > 28:
                name_text = name_text[:26] + ".."
            if is_selected:
                name_text = "▶ " + name_text
            flag = c4d.BFH_SCALEFIT
            self.AddButton(gid + OFFSET_BTN_SELECT, flag, 220, 16,
                           name=name_text)

            # 面数显示
            sort_val = format_number(s[self._SORT_KEY_MAP[self.sort_by]])
            self.AddStaticText(gid + OFFSET_BTN_SELECT + 100, c4d.BFH_RIGHT,
                               60, 0, name=sort_val)

            # 孤立按钮
            iso_label = "[O]" if not is_hidden else "[X]"
            self.AddButton(gid + OFFSET_BTN_ISOLATE, c4d.BFH_SCALEFIT,
                           32, 16, name=iso_label)

            # 减面按钮
            self.AddButton(gid + OFFSET_BTN_DECIMATE, c4d.BFH_SCALEFIT,
                           28, 16, name="[-]")

            self.GroupEnd()

        if len(stats) > MAX_DISPLAY:
            self.AddStaticText(0, c4d.BFH_SCALEFIT, 0, 0,
                               name=f"（仅显示前 {MAX_DISPLAY} 个，共 {len(stats)} 个网格体）")
            self.AddStaticText(0, c4d.BFH_SCALEFIT, 0, 0,
                               name="点击「刷新列表」或使用「导出 md 报表」查看全部")

        self.GroupEnd()
        self.LayoutChanged(GID_LIST_GROUP)

    @property
    def _SORT_KEY_MAP(self):
        return _SORT_KEY_MAP


# ──────────────────────────────────────────────
# Command — Entry point from menu/toolbar
# ──────────────────────────────────────────────
class MeshSorterCommand(c4d.plugins.CommandData):
    """命令入口：打开 Mesh Face Sorter 面板"""

    dialog = None

    def Execute(self, doc):
        if self.dialog is None or not self.dialog.IsOpen():
            self.dialog = MeshSorterDialog()
            self.dialog.Open(c4d.DLG_TYPE_ASYNC, PLUGIN_ID, -1, -1, 420, 500)
            # 对话框打开后触发首次扫描
            doc = c4d.documents.GetActiveDocument()
            if doc:
                stats = collect_mesh_stats(doc, force=False)
                _Cache.store(stats)
                self.dialog._update_status()
                self.dialog._update_stats(stats)
                self.dialog._build_list(stats)
        else:
            self.dialog.Close()
            self.dialog = None
        return True

    def RestoreLayout(self, sec_ref):
        """恢复对话框（C4D 面板停靠恢复时调用）"""
        if self.dialog is None:
            self.dialog = MeshSorterDialog()
        self.dialog.Open(c4d.DLG_TYPE_ASYNC, PLUGIN_ID, -1, -1, 420, 500)
        return True

    def GetResourceSymbol(self):
        return "C4D_MESH_FACE_SORTER"


# ──────────────────────────────────────────────
# Plugin registration
# ──────────────────────────────────────────────
def main():
    """插件入口函数（C4D 自动调用）"""

    # 注册命令
    icon_data = None  # 无图标，使用默认

    result = c4d.plugins.RegisterCommandPlugin(
        PLUGIN_ID,
        PLUGIN_NAME,
        c4d.PLUGINFLAG_COMMAND_HOTKEY,
        icon_data,
        PLUGIN_HELP,
        MeshSorterCommand(),
    )

    if not result:
        raise RuntimeError(f"Failed to register plugin: {PLUGIN_NAME}")

    print(f"[MeshFaceSorter] 插件已加载，ID: {PLUGIN_ID}")
    print(f"[MeshFaceSorter] 在菜单 扩展 > {PLUGIN_NAME} 中打开面板")


if __name__ == "__main__":
    main()
