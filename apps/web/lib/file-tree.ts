export interface TreeNode {
  name: string;
  path: string;
  type: "dir" | "file";
  children: TreeNode[];
}

/** Build a sorted directory tree (directories first) from a flat list of file paths. */
export function buildFileTree(paths: readonly string[]): TreeNode[] {
  const root: TreeNode = { name: "", path: "", type: "dir", children: [] };
  for (const raw of paths) {
    const parts = raw.split("/").filter(Boolean);
    let node = root;
    parts.forEach((part, i) => {
      const isFile = i === parts.length - 1;
      const path = parts.slice(0, i + 1).join("/");
      let child = node.children.find((c) => c.name === part && c.type === (isFile ? "file" : "dir"));
      if (!child) {
        child = { name: part, path, type: isFile ? "file" : "dir", children: [] };
        node.children.push(child);
      }
      node = child;
    });
  }
  const sort = (nodes: TreeNode[]) => {
    nodes.sort((a, b) => (a.type === b.type ? a.name.localeCompare(b.name) : a.type === "dir" ? -1 : 1));
    nodes.forEach((n) => sort(n.children));
  };
  sort(root.children);
  return root.children;
}
