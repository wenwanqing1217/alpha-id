"""SkillRepository — Git-based 技能发现与安装

去中心化技能仓库协议：
- 任何 Git 仓库或本地目录可作为一个 Skill Repository
- 标准目录结构：
  repository.json           # 仓库元数据
  skills/
    <name>/
      skill.py              # 技能文件
      package.json          # 签名包元数据（可选，如果没有则从 registry 获取）
      README.md             # 文档（可选）
- 作者通过 DID 签名技能包
- 用户通过 DID 解析找到作者的仓库

用法：
    repo = SkillRepository()
    skills = repo.scan("/path/to/repo")
    repo.install(skills[0], registry=my_registry)
"""

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import List, Optional, Union

from alpha_id.did_resolver import DIDResolver
from alpha_id.signer import AIDSigner
from alpha_id.skill_signer import SkillPackage, SkillRegistry, SkillSigningError, sign_skill

# ── 仓库协议版本 ──

REPOSITORY_SPEC_VERSION = "1.0"

# ── 标准目录结构 ──

REPOSITORY_META_FILE = "repository.json"
SKILLS_DIR = "skills"
SKILL_FILE = "skill.py"
PACKAGE_FILE = "package.json"
SKILL_README = "README.md"


@dataclass
class RepositoryMeta:
    """仓库元数据"""

    name: str
    description: str = ""
    author_did: str = ""
    version: str = REPOSITORY_SPEC_VERSION
    website: str = ""
    skills: List[str] = field(default_factory=list)

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, indent=2)

    @classmethod
    def from_json(cls, text: str) -> "RepositoryMeta":
        data = json.loads(text)
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class RepositorySkill:
    """从仓库扫描到的技能"""

    name: str
    repo_path: Path
    skill_file: Path
    package_file: Optional[Path] = None
    readme_file: Optional[Path] = None
    description: str = ""
    author_did: str = ""
    version: str = ""
    is_signed: bool = False


class SkillRepository:
    """去中心化技能仓库 — 从目录/Git 仓库发现并安装技能"""

    def __init__(self, resolver: Optional[DIDResolver] = None):
        self._resolver = resolver or DIDResolver()

    # ── 仓库发现 ──

    def scan(self, repo_path: Union[str, Path]) -> List[RepositorySkill]:
        """扫描本地仓库目录，发现所有可用技能

        Args:
            repo_path: 仓库根目录路径

        Returns:
            发现的技能列表
        """
        repo_path = Path(repo_path).expanduser().resolve()
        if not repo_path.is_dir():
            return []

        skills_dir = repo_path / SKILLS_DIR
        if not skills_dir.is_dir():
            return []

        results: List[RepositorySkill] = []
        for skill_dir in sorted(skills_dir.iterdir()):
            if not skill_dir.is_dir():
                continue
            name = skill_dir.name
            skill_file = skill_dir / SKILL_FILE
            if not skill_file.is_file():
                continue

            pkg_file = skill_dir / PACKAGE_FILE
            readme_file = skill_dir / SKILL_README

            # 读取元数据（从 package.json 或仓库 meta）
            description = ""
            author_did = ""
            version = ""
            is_signed = False

            if pkg_file.is_file():
                try:
                    pkg_data = json.loads(pkg_file.read_text(encoding="utf-8"))
                    description = pkg_data.get("description", "")
                    author_did = pkg_data.get("author_did", "")
                    version = pkg_data.get("version", "")
                    is_signed = bool(pkg_data.get("signature"))
                except (json.JSONDecodeError, KeyError):
                    pass

            results.append(
                RepositorySkill(
                    name=name,
                    repo_path=repo_path,
                    skill_file=skill_file,
                    package_file=pkg_file if pkg_file.is_file() else None,
                    readme_file=readme_file if readme_file.is_file() else None,
                    description=description,
                    author_did=author_did,
                    version=version,
                    is_signed=is_signed,
                )
            )

        return results

    def scan_github(self, repo_url: str, local_clone_dir: Optional[Union[str, Path]] = None) -> List[RepositorySkill]:
        """扫描 GitHub 仓库（需要 git 已 clone）

        Args:
            repo_url: GitHub 仓库 URL
            local_clone_dir: 本地已 clone 的目录（如果为 None，尝试推断）

        Returns:
            发现的技能列表
        """
        if local_clone_dir is None:
            # 从 URL 推断本地目录名
            repo_name = repo_url.rstrip("/").split("/")[-1]
            if repo_name.endswith(".git"):
                repo_name = repo_name[:-4]
            local_clone_dir = Path.cwd() / repo_name

        return self.scan(local_clone_dir)

    # ── 仓库初始化 ──

    def init_repo(
        self, repo_path: Union[str, Path], name: str, description: str = "", author_did: str = ""
    ) -> RepositoryMeta:
        """初始化一个新的技能仓库目录

        Args:
            repo_path: 仓库根目录
            name: 仓库名称
            description: 仓库描述
            author_did: 作者 DID

        Returns:
            仓库元数据
        """
        repo_path = Path(repo_path).expanduser().resolve()
        repo_path.mkdir(parents=True, exist_ok=True)
        (repo_path / SKILLS_DIR).mkdir(exist_ok=True)

        meta = RepositoryMeta(
            name=name,
            description=description,
            author_did=author_did,
        )
        meta_file = repo_path / REPOSITORY_META_FILE
        meta_file.write_text(meta.to_json(), encoding="utf-8")
        return meta

    # ── 技能发布 ──

    def publish_skill(
        self,
        repo_path: Union[str, Path],
        skill_file: Union[str, Path],
        signer: AIDSigner,
        name: str,
        version: str = "1.0.0",
        description: str = "",
        force: bool = False,
    ) -> RepositorySkill:
        """将技能发布到仓库

        1. 签名技能文件
        2. 复制到仓库标准的 skills/<name>/ 目录
        3. 生成 package.json

        Args:
            repo_path: 仓库根目录
            skill_file: 技能源文件路径
            signer: 作者的签名器
            name: 技能名称
            version: 版本号
            description: 描述
            force: 是否覆盖已有

        Returns:
            发布的技能信息
        """
        repo_path = Path(repo_path).expanduser().resolve()
        skill_file = Path(skill_file).expanduser().resolve()
        target_dir = repo_path / SKILLS_DIR / name
        target_file = target_dir / SKILL_FILE
        pkg_file = target_dir / PACKAGE_FILE

        if target_file.exists() and not force:
            raise FileExistsError(f"技能已存在: {target_dir} （使用 force=True 覆盖）")

        target_dir.mkdir(parents=True, exist_ok=True)

        # 签名
        pkg = sign_skill(skill_file, signer, name=name, version=version, description=description)

        # 复制技能文件
        import shutil

        shutil.copy2(str(skill_file), str(target_file))

        # 写 package.json
        pkg_file.write_text(
            json.dumps(
                {
                    "name": pkg.name,
                    "version": pkg.version,
                    "author_did": pkg.author_did,
                    "author_public_key_hex": pkg.author_public_key_hex,
                    "description": pkg.description or description,
                    "content_hash": pkg.content_hash,
                    "content_type": pkg.content_type,
                    "signature": pkg.signature,
                    "signed_at": pkg.signed_at,
                    "tags": pkg.tags,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        # 更新仓库元数据
        meta_file = repo_path / REPOSITORY_META_FILE
        if meta_file.exists():
            meta = RepositoryMeta.from_json(meta_file.read_text(encoding="utf-8"))
        else:
            meta = RepositoryMeta(name=repo_path.name, author_did=signer.did)
        if name not in meta.skills:
            meta.skills.append(name)
        meta_file.write_text(meta.to_json(), encoding="utf-8")

        return RepositorySkill(
            name=name,
            repo_path=repo_path,
            skill_file=target_file,
            package_file=pkg_file,
            description=description,
            author_did=signer.did,
            version=version,
            is_signed=True,
        )

    def install_skill(self, skill: RepositorySkill, registry: SkillRegistry) -> dict:
        """从仓库安装技能到本地注册表

        Args:
            skill: 仓库中扫描到的技能
            registry: 目标注册表

        Returns:
            注册结果

        Raises:
            SkillSigningError: 技能未签名（拒绝安装未签名技能）
        """
        # 读取或拒绝未签名技能
        content = skill.skill_file.read_bytes()

        if skill.package_file and skill.package_file.exists():
            # 有 package.json，尝试构建 SkillPackage
            pkg_data = json.loads(skill.package_file.read_text(encoding="utf-8"))
            pkg = SkillPackage(
                name=pkg_data.get("name", skill.name),
                version=pkg_data.get("version", "1.0.0"),
                author_did=pkg_data.get("author_did", ""),
                description=pkg_data.get("description", ""),
                author_public_key_hex=pkg_data.get("author_public_key_hex", ""),
                content_hash=pkg_data.get("content_hash", ""),
                content_type=pkg_data.get("content_type", "python"),
                signature=pkg_data.get("signature", ""),
                signed_at=pkg_data.get("signed_at", 0.0),
                tags=pkg_data.get("tags", []),
            )
        else:
            # 无 package.json，检查扫描时是否检测到签名
            if not skill.is_signed:
                raise SkillSigningError(
                    f"技能 '{skill.name}' 未签名，拒绝安装。请让作者先签名技能。"
                )
            # 有签名但无 package.json（扫描时检测到签名）
            pkg = SkillPackage(
                name=skill.name,
                version=skill.version or "1.0.0",
                author_did=skill.author_did,
                description=skill.description,
                content_hash="",
                content_type="python",
                signature="",
                signed_at=0.0,
            )

        # 拒绝未签名技能（有 package.json 但无签名的情况）
        if not pkg.is_signed:
            raise SkillSigningError(
                f"技能 '{skill.name}' 未签名，拒绝安装。请让作者先签名技能。"
            )

        # 注册
        return registry.register(pkg, content=content)

    # ── 仓库信息 ──

    def get_repo_meta(self, repo_path: Union[str, Path]) -> Optional[RepositoryMeta]:
        """读取仓库元数据"""
        repo_path = Path(repo_path).expanduser().resolve()
        meta_file = repo_path / REPOSITORY_META_FILE
        if not meta_file.exists():
            return None
        try:
            return RepositoryMeta.from_json(meta_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, KeyError):
            return None
