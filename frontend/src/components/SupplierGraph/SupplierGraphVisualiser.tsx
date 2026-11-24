/**
 * Supplier Graph Visualiser Component (P12-5)
 *
 * Interactive Canvas/SVG Force-Directed and Hierarchical Subgraph Visualizer:
 * - Renders 2-hop topological ego-subgraph from Neptune (GET /api/v1/suppliers/{id}/graph).
 * - Full zoom, pan, and interactive node drag & drop.
 * - Hierarchical DAG layer layout, Spring force physics simulation, and Radial layout.
 * - Critical failure path tracing (dashed red glow) from NanoCore to vehicle assembly.
 * - Qualified AML secondary supply path tracing (dashed emerald).
 * - Click-to-inspect node details and blast radius telemetry.
 */

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  type GraphEdge,
  type GraphNode,
  useGraphStore,
} from '../../stores/useGraphStore';

const CANVAS_WIDTH = 1400;
const CANVAS_HEIGHT = 650;

export const SupplierGraphVisualiser: React.FC = () => {
  const {
    graphData,
    selectedNodeId,
    selectNode,
    selectEdge,
    searchQuery,
    filterTier,
    filterNodeType,
    isPathHighlightActive,
    criticalPathNodeIds,
    layoutMode,
    isSimulating,
    zoom,
    pan,
    setPan,
    setZoom,
    updateNodePosition,
  } = useGraphStore();

  const svgRef = useRef<SVGSVGElement | null>(null);

  // Drag & Pan state
  const [isPanning, setIsPanning] = useState(false);
  const [panStart, setPanStart] = useState({ x: 0, y: 0 });
  const [draggingNodeId, setDraggingNodeId] = useState<string | null>(null);
  const [hoveredNodeId, setHoveredNodeId] = useState<string | null>(null);
  const [hoveredEdge, setHoveredEdge] = useState<GraphEdge | null>(null);

  // ---------------------------------------------------------------------------
  // Force Simulation Physics Loop (when isSimulating is active)
  // ---------------------------------------------------------------------------
  useEffect(() => {
    if (!isSimulating || !graphData || layoutMode !== 'force') return;

    let animFrame: number;

    const simulateStep = () => {
      const nodes = [...graphData.nodes];
      const edges = graphData.edges;

      // Physics parameters
      const kRepulsion = 45000;
      const kSpring = 0.04;
      const springLength = 180;
      const damping = 0.82;
      const centerGravity = 0.015;
      const centerX = CANVAS_WIDTH / 2;
      const centerY = CANVAS_HEIGHT / 2;

      // 1. Repulsion between all pairs of nodes
      for (let i = 0; i < nodes.length; i++) {
        for (let j = i + 1; j < nodes.length; j++) {
          const n1 = nodes[i];
          const n2 = nodes[j];
          const x1 = n1.x ?? centerX;
          const y1 = n1.y ?? centerY;
          const x2 = n2.x ?? centerX;
          const y2 = n2.y ?? centerY;

          const dx = x2 - x1;
          const dy = y2 - y1;
          const distSq = dx * dx + dy * dy + 100;
          const dist = Math.sqrt(distSq);

          const force = kRepulsion / distSq;
          const fx = (dx / dist) * force;
          const fy = (dy / dist) * force;

          n1.vx = (n1.vx ?? 0) - fx;
          n1.vy = (n1.vy ?? 0) - fy;
          n2.vx = (n2.vx ?? 0) + fx;
          n2.vy = (n2.vy ?? 0) + fy;
        }
      }

      // 2. Spring attraction along connected edges
      const nodeIndexMap = new Map<string, GraphNode>();
      nodes.forEach((n) => nodeIndexMap.set(n.id, n));

      edges.forEach((edge) => {
        const src = nodeIndexMap.get(edge.source);
        const tgt = nodeIndexMap.get(edge.target);
        if (!src || !tgt) return;

        const x1 = src.x ?? centerX;
        const y1 = src.y ?? centerY;
        const x2 = tgt.x ?? centerX;
        const y2 = tgt.y ?? centerY;

        const dx = x2 - x1;
        const dy = y2 - y1;
        const dist = Math.sqrt(dx * dx + dy * dy) || 1;
        const displacement = dist - springLength;

        const force = kSpring * displacement;
        const fx = (dx / dist) * force;
        const fy = (dy / dist) * force;

        src.vx = (src.vx ?? 0) + fx;
        src.vy = (src.vy ?? 0) + fy;
        tgt.vx = (tgt.vx ?? 0) - fx;
        tgt.vy = (tgt.vy ?? 0) - fy;
      });

      // 3. Center gravity and update positions
      nodes.forEach((n) => {
        if (n.id === draggingNodeId) return; // Keep dragging node pinned to cursor

        const curX = n.x ?? centerX;
        const curY = n.y ?? centerY;

        // Gravitational pull toward canvas center
        n.vx = ((n.vx ?? 0) + (centerX - curX) * centerGravity) * damping;
        n.vy = ((n.vy ?? 0) + (centerY - curY) * centerGravity) * damping;

        // Update position bounded inside canvas
        const nextX = Math.max(60, Math.min(CANVAS_WIDTH - 60, curX + (n.vx ?? 0)));
        const nextY = Math.max(60, Math.min(CANVAS_HEIGHT - 60, curY + (n.vy ?? 0)));

        updateNodePosition(n.id, nextX, nextY);
      });

      animFrame = requestAnimationFrame(simulateStep);
    };

    animFrame = requestAnimationFrame(simulateStep);
    return () => cancelAnimationFrame(animFrame);
  }, [isSimulating, graphData, layoutMode, draggingNodeId, updateNodePosition]);

  // ---------------------------------------------------------------------------
  // Radial Layout Calculation (when layoutMode === 'radial')
  // ---------------------------------------------------------------------------
  const radialPositionedNodes = useMemo(() => {
    if (!graphData || layoutMode !== 'radial') return graphData?.nodes || [];

    const rootId = selectedNodeId || graphData.supplier_id || 'SUP-NC-001';
    const centerX = CANVAS_WIDTH / 2;
    const centerY = CANVAS_HEIGHT / 2;

    // BFS distance from root
    const distMap = new Map<string, number>();
    distMap.set(rootId, 0);

    const queue: string[] = [rootId];
    while (queue.length > 0) {
      const curr = queue.shift()!;
      const currDist = distMap.get(curr)!;

      // Find neighbors
      const neighbors = graphData.edges
        .filter((e) => e.source === curr || e.target === curr)
        .map((e) => (e.source === curr ? e.target : e.source));

      neighbors.forEach((nbr) => {
        if (!distMap.has(nbr)) {
          distMap.set(nbr, currDist + 1);
          queue.push(nbr);
        }
      });
    }

    // Group nodes by ring
    const rings: Record<number, GraphNode[]> = {};
    graphData.nodes.forEach((n) => {
      const ring = distMap.get(n.id) ?? 3;
      rings[ring] = rings[ring] || [];
      rings[ring].push(n);
    });

    const ringRadii = [0, 160, 290, 420];

    const result: GraphNode[] = [];
    Object.entries(rings).forEach(([ringStr, rNodes]) => {
      const ringIndex = Math.min(Number(ringStr), 3);
      const radius = ringRadii[ringIndex];
      const count = rNodes.length;

      rNodes.forEach((node, idx) => {
        if (ringIndex === 0) {
          result.push({ ...node, x: centerX, y: centerY });
        } else {
          const angle = (idx / count) * 2 * Math.PI - Math.PI / 2;
          result.push({
            ...node,
            x: centerX + radius * Math.cos(angle),
            y: centerY + radius * Math.sin(angle),
          });
        }
      });
    });

    return result;
  }, [graphData, layoutMode, selectedNodeId]);

  const activeNodes = layoutMode === 'radial' ? radialPositionedNodes : graphData?.nodes || [];

  const nodeMap = useMemo(() => {
    const map = new Map<string, GraphNode>();
    activeNodes.forEach((n) => map.set(n.id, n));
    return map;
  }, [activeNodes]);

  // ---------------------------------------------------------------------------
  // Node Matching and Filtering
  // ---------------------------------------------------------------------------
  const isNodeVisible = useCallback(
    (node: GraphNode): boolean => {
      if (filterTier !== 'ALL' && node.node_type === 'supplier' && node.tier !== filterTier) {
        return false;
      }
      if (filterNodeType !== 'ALL' && node.node_type !== filterNodeType) {
        return false;
      }
      return true;
    },
    [filterTier, filterNodeType]
  );

  const isNodeSearched = useCallback(
    (node: GraphNode): boolean => {
      if (!searchQuery.trim()) return true;
      const q = searchQuery.toLowerCase();
      return (
        node.id.toLowerCase().includes(q) ||
        node.name.toLowerCase().includes(q) ||
        Boolean(node.sku?.toLowerCase().includes(q)) ||
        Boolean(node.location?.toLowerCase().includes(q))
      );
    },
    [searchQuery]
  );

  // ---------------------------------------------------------------------------
  // Canvas Pan & Zoom Handlers
  // ---------------------------------------------------------------------------
  const handleMouseDown = (e: React.MouseEvent<SVGSVGElement>) => {
    if ((e.target as HTMLElement).tagName === 'svg' || (e.target as HTMLElement).id === 'canvas-bg') {
      setIsPanning(true);
      setPanStart({ x: e.clientX - pan.x, y: e.clientY - pan.y });
    }
  };

  const handleMouseMove = (e: React.MouseEvent<SVGSVGElement>) => {
    if (isPanning) {
      setPan({ x: e.clientX - panStart.x, y: e.clientY - panStart.y });
    } else if (draggingNodeId) {
      const svg = svgRef.current;
      if (!svg) return;
      const rect = svg.getBoundingClientRect();
      const clientX = e.clientX - rect.left;
      const clientY = e.clientY - rect.top;

      // Inverse transform from pan and zoom
      const unprojectedX = (clientX - pan.x) / zoom;
      const unprojectedY = (clientY - pan.y) / zoom;

      updateNodePosition(draggingNodeId, unprojectedX, unprojectedY);
    }
  };

  const handleMouseUp = () => {
    setIsPanning(false);
    setDraggingNodeId(null);
  };

  const handleWheel = (e: React.WheelEvent<SVGSVGElement>) => {
    e.preventDefault();
    const zoomFactor = e.deltaY < 0 ? 1.08 : 0.92;
    setZoom(zoom * zoomFactor);
  };

  if (!graphData) {
    return (
      <div className="w-full h-[650px] bg-[#060911] border border-slate-800 rounded-xl flex items-center justify-center text-slate-500 text-sm">
        No graph data loaded. Please select a supplier to visualize.
      </div>
    );
  }

  return (
    <div className="relative w-full h-[650px] bg-[#060911] border border-slate-800 rounded-xl overflow-hidden select-none">
      {/* SVG Interactive Canvas */}
      <svg
        ref={svgRef}
        id="supplier-graph-canvas"
        className="w-full h-full cursor-grab active:cursor-grabbing"
        viewBox={`0 0 ${CANVAS_WIDTH} ${CANVAS_HEIGHT}`}
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
        onMouseLeave={handleMouseUp}
        onWheel={handleWheel}
      >
        <defs>
          {/* Glowing Filter for Disrupted Critical Failure Path */}
          <filter id="glow-rose" x="-20%" y="-20%" width="140%" height="140%">
            <feDropShadow dx="0" dy="0" stdDeviation="5" floodColor="#f43f5e" floodOpacity="0.8" />
          </filter>

          {/* Glowing Filter for Qualified AML Alternate Path */}
          <filter id="glow-emerald" x="-20%" y="-20%" width="140%" height="140%">
            <feDropShadow dx="0" dy="0" stdDeviation="4" floodColor="#10b981" floodOpacity="0.7" />
          </filter>

          {/* Standard Arrow Marker */}
          <marker
            id="arrow"
            viewBox="0 0 10 10"
            refX="24"
            refY="5"
            markerWidth="6"
            markerHeight="6"
            orient="auto-start-reverse"
          >
            <path d="M 0 1 L 9 5 L 0 9 z" fill="#64748b" />
          </marker>

          {/* Red Marker for Critical Path */}
          <marker
            id="arrow-red"
            viewBox="0 0 10 10"
            refX="26"
            refY="5"
            markerWidth="6.5"
            markerHeight="6.5"
            orient="auto-start-reverse"
          >
            <path d="M 0 1 L 9 5 L 0 9 z" fill="#f43f5e" />
          </marker>

          {/* Green Marker for AML Alternate Route */}
          <marker
            id="arrow-green"
            viewBox="0 0 10 10"
            refX="24"
            refY="5"
            markerWidth="6"
            markerHeight="6"
            orient="auto-start-reverse"
          >
            <path d="M 0 1 L 9 5 L 0 9 z" fill="#10b981" />
          </marker>
        </defs>

        {/* Canvas Background Click Target */}
        <rect id="canvas-bg" width="100%" height="100%" fill="transparent" />

        {/* Zoom & Pan Container */}
        <g transform={`translate(${pan.x}, ${pan.y}) scale(${zoom})`}>
          {/* Radial Concentric Guides (when radial mode active) */}
          {layoutMode === 'radial' && (
            <g opacity={0.15}>
              <circle cx={CANVAS_WIDTH / 2} cy={CANVAS_HEIGHT / 2} r={160} fill="none" stroke="#38bdf8" strokeDasharray="4,4" />
              <circle cx={CANVAS_WIDTH / 2} cy={CANVAS_HEIGHT / 2} r={290} fill="none" stroke="#38bdf8" strokeDasharray="4,4" />
              <circle cx={CANVAS_WIDTH / 2} cy={CANVAS_HEIGHT / 2} r={420} fill="none" stroke="#38bdf8" strokeDasharray="4,4" />
            </g>
          )}

          {/* 1. EDGES */}
          <g id="graph-edges">
            {graphData.edges.map((edge, index) => {
              const src = nodeMap.get(edge.source);
              const tgt = nodeMap.get(edge.target);
              if (!src || !tgt) return null;

              const x1 = src.x ?? CANVAS_WIDTH / 2;
              const y1 = src.y ?? CANVAS_HEIGHT / 2;
              const x2 = tgt.x ?? CANVAS_WIDTH / 2;
              const y2 = tgt.y ?? CANVAS_HEIGHT / 2;

              // Check if edge is on the canonical critical failure path
              const isCriticalEdge =
                isPathHighlightActive &&
                criticalPathNodeIds.includes(edge.source) &&
                criticalPathNodeIds.includes(edge.target) &&
                edge.is_disrupted;

              const isAlternate = edge.is_alternate;

              // Compute mid-point for relationship badge
              const midX = (x1 + x2) / 2;
              const midY = (y1 + y2) / 2;

              return (
                <g
                  key={`edge-${edge.source}-${edge.target}-${index}`}
                  className="cursor-pointer transition-opacity"
                  onClick={() => selectEdge(edge)}
                  onMouseEnter={() => setHoveredEdge(edge)}
                  onMouseLeave={() => setHoveredEdge(null)}
                >
                  {/* Invisible thicker stroke for easy clicking/hovering */}
                  <line x1={x1} y1={y1} x2={x2} y2={y2} stroke="transparent" strokeWidth="18" />

                  {/* Visual Edge Path */}
                  <line
                    x1={x1}
                    y1={y1}
                    x2={x2}
                    y2={y2}
                    stroke={
                      isCriticalEdge
                        ? '#f43f5e'
                        : isAlternate
                        ? '#10b981'
                        : '#334155'
                    }
                    strokeWidth={isCriticalEdge ? 3.5 : isAlternate ? 2.5 : 1.75}
                    strokeDasharray={
                      isCriticalEdge
                        ? '6,4'
                        : isAlternate
                        ? '4,4'
                        : undefined
                    }
                    filter={isCriticalEdge ? 'url(#glow-rose)' : isAlternate ? 'url(#glow-emerald)' : undefined}
                    markerEnd={
                      isCriticalEdge
                        ? 'url(#arrow-red)'
                        : isAlternate
                        ? 'url(#arrow-green)'
                        : 'url(#arrow)'
                    }
                  />

                  {/* Edge Relationship Label Badge */}
                  {edge.label && (
                    <g transform={`translate(${midX}, ${midY})`}>
                      <rect
                        x="-48"
                        y="-10"
                        width="96"
                        height="20"
                        rx="4"
                        fill={isCriticalEdge ? '#4c0519' : '#0b1120'}
                        stroke={isCriticalEdge ? '#f43f5e' : '#334155'}
                        strokeWidth="1"
                        opacity={0.92}
                      />
                      <text
                        x="0"
                        y="3"
                        fontSize="8.5"
                        textAnchor="middle"
                        fill={isCriticalEdge ? '#fda4af' : '#94a3b8'}
                        fontWeight={isCriticalEdge ? '700' : '500'}
                        fontFamily="monospace"
                      >
                        {edge.relationship.slice(0, 13)}
                      </text>
                    </g>
                  )}
                </g>
              );
            })}
          </g>

          {/* 2. NODES */}
          <g id="graph-nodes">
            {activeNodes.map((node) => {
              const visible = isNodeVisible(node);
              const searched = isNodeSearched(node);
              const isSelected = selectedNodeId === node.id;
              const isHovered = hoveredNodeId === node.id;
              const isCritical =
                isPathHighlightActive && criticalPathNodeIds.includes(node.id);

              const x = node.x ?? CANVAS_WIDTH / 2;
              const y = node.y ?? CANVAS_HEIGHT / 2;

              const opacity = !visible || !searched ? 0.25 : 1;

              return (
                <g
                  key={node.id}
                  transform={`translate(${x}, ${y})`}
                  opacity={opacity}
                  className="cursor-pointer transition-transform"
                  onClick={() => selectNode(node.id)}
                  onMouseDown={(e) => {
                    e.stopPropagation();
                    setDraggingNodeId(node.id);
                  }}
                  onMouseEnter={() => setHoveredNodeId(node.id)}
                  onMouseLeave={() => setHoveredNodeId(null)}
                >
                  {/* Selection Pulsing Ring */}
                  {isSelected && (
                    <circle
                      r="46"
                      fill="none"
                      stroke="#38bdf8"
                      strokeWidth="2.5"
                      strokeDasharray="5,4"
                      className="animate-spin"
                    />
                  )}

                  {/* Hover Accent Ring */}
                  {isHovered && !isSelected && (
                    <circle
                      r="42"
                      fill="none"
                      stroke="#38bdf8"
                      strokeWidth="1.5"
                      opacity={0.6}
                    />
                  )}

                  {/* Critical Path Pulsing Ring */}
                  {isCritical && !isSelected && (
                    <circle
                      r="44"
                      fill="none"
                      stroke="#f43f5e"
                      strokeWidth="2"
                      filter="url(#glow-rose)"
                    />
                  )}

                  {/* Node Shape by Node Type */}
                  {node.node_type === 'supplier' ? (
                    // Supplier: Circle
                    <g>
                      <circle
                        r={node.status === 'DISRUPTED' ? 36 : 30}
                        fill={
                          node.status === 'DISRUPTED'
                            ? '#4c0519'
                            : node.aml_status
                            ? '#064e3b'
                            : node.tier === 1
                            ? '#0c4a6e'
                            : '#1e293b'
                        }
                        stroke={
                          node.status === 'DISRUPTED'
                            ? '#f43f5e'
                            : node.aml_status
                            ? '#10b981'
                            : node.tier === 1
                            ? '#0ea5e9'
                            : '#64748b'
                        }
                        strokeWidth={node.status === 'DISRUPTED' ? 3 : 2}
                        filter={
                          node.status === 'DISRUPTED'
                            ? 'url(#glow-rose)'
                            : node.aml_status
                            ? 'url(#glow-emerald)'
                            : undefined
                        }
                      />
                      <text
                        y="-6"
                        fontSize="9"
                        textAnchor="middle"
                        fill={
                          node.status === 'DISRUPTED'
                            ? '#fca5a5'
                            : node.aml_status
                            ? '#a7f3d0'
                            : '#bae6fd'
                        }
                        fontWeight="800"
                        letterSpacing="0.05em"
                      >
                        {node.aml_status ? 'AML' : `TIER-${node.tier || 1}`}
                      </text>
                      <text
                        y="8"
                        fontSize="9.5"
                        textAnchor="middle"
                        fill="#ffffff"
                        fontWeight="700"
                      >
                        {node.name.length > 12 ? `${node.name.slice(0, 11)}…` : node.name}
                      </text>
                    </g>
                  ) : node.node_type === 'component' ? (
                    // Component: Rounded Rect
                    <g transform="translate(-48, -24)">
                      <rect
                        width="96"
                        height="48"
                        rx="8"
                        fill="#1e1b4b"
                        stroke={node.is_single_source ? '#818cf8' : '#6366f1'}
                        strokeWidth="2"
                      />
                      <text
                        x="48"
                        y="16"
                        fontSize="8.5"
                        textAnchor="middle"
                        fill="#a5b4fc"
                        fontWeight="800"
                      >
                        PART SKU
                      </text>
                      <text
                        x="48"
                        y="30"
                        fontSize="10"
                        textAnchor="middle"
                        fill="#ffffff"
                        fontFamily="monospace"
                        fontWeight="700"
                      >
                        {node.sku || node.id}
                      </text>
                      <text
                        x="48"
                        y="41"
                        fontSize="7.5"
                        textAnchor="middle"
                        fill="#c7d2fe"
                      >
                        {node.days_of_cover ? `${node.days_of_cover.toFixed(1)}d cover` : ''}
                      </text>
                    </g>
                  ) : node.node_type === 'plant' ? (
                    // Plant: Rounded Box
                    <g transform="translate(-50, -26)">
                      <rect
                        width="100"
                        height="52"
                        rx="10"
                        fill="#042f2e"
                        stroke={node.status === 'CRITICAL_HALT_WARNING' ? '#f43f5e' : '#14b8a6'}
                        strokeWidth="2.5"
                      />
                      <text
                        x="50"
                        y="17"
                        fontSize="8.5"
                        textAnchor="middle"
                        fill="#5eead4"
                        fontWeight="800"
                      >
                        PLANT
                      </text>
                      <text
                        x="50"
                        y="31"
                        fontSize="10"
                        textAnchor="middle"
                        fill="#ffffff"
                        fontWeight="700"
                      >
                        {node.name.split(' ')[0]}
                      </text>
                      <text
                        x="50"
                        y="44"
                        fontSize="8"
                        textAnchor="middle"
                        fill={node.status === 'CRITICAL_HALT_WARNING' ? '#fb7185' : '#99f6e4'}
                        fontWeight="600"
                      >
                        {node.halt_rate_eur_per_hr ? `€${Math.round(node.halt_rate_eur_per_hr / 1000)}k/hr` : ''}
                      </text>
                    </g>
                  ) : (
                    // Program: Rounded Diamond/Pill
                    <g transform="translate(-54, -22)">
                      <rect
                        width="108"
                        height="44"
                        rx="8"
                        fill="#431407"
                        stroke="#f97316"
                        strokeWidth="2"
                      />
                      <text
                        x="54"
                        y="16"
                        fontSize="8.5"
                        textAnchor="middle"
                        fill="#fed7aa"
                        fontWeight="800"
                      >
                        PROGRAM
                      </text>
                      <text
                        x="54"
                        y="30"
                        fontSize="9.5"
                        textAnchor="middle"
                        fill="#ffffff"
                        fontWeight="700"
                      >
                        {node.name.length > 14 ? `${node.name.slice(0, 13)}…` : node.name}
                      </text>
                    </g>
                  )}

                  {/* Sub-label banner under node */}
                  <text
                    y="46"
                    fontSize="9"
                    textAnchor="middle"
                    fill={isCritical ? '#fb7185' : '#94a3b8'}
                    fontWeight={isCritical ? '700' : '500'}
                  >
                    {node.disruption_event
                      ? '🔥 Fab Fire Disrupted'
                      : node.aml_status
                      ? '✅ AML Qualified'
                      : node.is_single_source
                      ? '⚠️ Single Source'
                      : ''}
                  </text>
                </g>
              );
            })}
          </g>
        </g>
      </svg>

      {/* Floating Status Bar / Quick Stats */}
      <div className="absolute bottom-3 left-4 bg-[#080d1a]/85 backdrop-blur border border-slate-800 rounded-lg px-3 py-1.5 text-[11px] font-mono text-slate-400 flex items-center gap-3">
        <span>Nodes: <strong className="text-white">{activeNodes.length}</strong></span>
        <span>Edges: <strong className="text-white">{graphData.edges.length}</strong></span>
        <span>Depth: <strong className="text-sky-400">2 Hops</strong></span>
        {isPathHighlightActive && (
          <span className="text-rose-400 font-semibold flex items-center gap-1">
            <span className="w-1.5 h-1.5 rounded-full bg-rose-500 animate-ping" />
            Critical Path Active ({criticalPathNodeIds.length} nodes)
          </span>
        )}
      </div>

      {/* Edge Hover Tooltip */}
      {hoveredEdge && (
        <div className="absolute top-4 left-4 bg-slate-900/90 backdrop-blur border border-slate-700 rounded-lg p-2.5 text-xs text-slate-200 shadow-xl pointer-events-none">
          <div className="font-semibold text-sky-400 font-mono">
            {hoveredEdge.relationship}
          </div>
          <div className="text-[11px] text-slate-300 mt-0.5">
            {hoveredEdge.source} &rarr; {hoveredEdge.target}
          </div>
          {hoveredEdge.label && (
            <div className="text-[10px] text-slate-400 mt-1 italic">
              {hoveredEdge.label}
            </div>
          )}
        </div>
      )}
    </div>
  );
};
