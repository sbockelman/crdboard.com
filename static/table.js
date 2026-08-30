(async function () {
  const tableId = Number(document.body.dataset.tableId);
  const statusEl = document.getElementById("status");
  const surfaceEl = document.getElementById("table-surface");
  const presenceEl = document.getElementById("presence");
  const state = {
    objects: new Map(),
    selectedObjectId: null,
    pendingClientOps: new Set(),
    lastEventSeq: 0,
    drag: null,
  };

  function log(msg, data) {
    statusEl.textContent = `${msg}${data ? ` ${JSON.stringify(data)}` : ""}\n` + statusEl.textContent;
  }

  function renderPresence(presence) {
    presenceEl.textContent = `Players: ${presence.map((p) => p.username).join(", ")}`;
  }

  function upsertObject(obj) {
    state.objects.set(obj.id, obj);
    let el = document.getElementById(`obj-${obj.id}`);
    if (!el) {
      el = document.createElement("div");
      el.id = `obj-${obj.id}`;
      el.className = "obj";
      el.addEventListener("click", () => {
        state.selectedObjectId = obj.id;
      });
      enableDragging(el, obj.id);
      surfaceEl.appendChild(el);
    }
    el.classList.remove("front", "back");
    el.classList.add(obj.face);
    el.style.left = `${obj.position.x}px`;
    el.style.top = `${obj.position.y}px`;
    el.style.transform = `rotate(${obj.rotation}deg)`;
    el.style.zIndex = String(obj.zIndex);
    el.textContent = obj.metadata?.label || obj.sourceId || obj.id.slice(0, 6);
  }

  function applyEvent(event) {
    state.lastEventSeq = Math.max(state.lastEventSeq, event.seq || 0);
    if (event.eventType === "object.operation") {
      upsertObject(event.payload.state);
    }
  }

  function enableDragging(el, objectId) {
    el.addEventListener("mousedown", (e) => {
      state.drag = {
        objectId,
        startX: e.clientX,
        startY: e.clientY,
      };
      el.style.cursor = "grabbing";
      state.selectedObjectId = objectId;
    });
  }

  window.addEventListener("mousemove", (e) => {
    if (!state.drag) return;
    const obj = state.objects.get(state.drag.objectId);
    if (!obj) return;
    const dx = e.clientX - state.drag.startX;
    const dy = e.clientY - state.drag.startY;
    state.drag.startX = e.clientX;
    state.drag.startY = e.clientY;
    obj.position.x += dx;
    obj.position.y += dy;
    upsertObject(obj);
  });

  window.addEventListener("mouseup", () => {
    if (!state.drag) return;
    const objectId = state.drag.objectId;
    state.drag = null;
    const obj = state.objects.get(objectId);
    const el = document.getElementById(`obj-${objectId}`);
    if (el) el.style.cursor = "grab";
    if (!obj) return;
    sendOperation("move", { objectId, position: obj.position });
  });

  const connResp = await fetch(`/api/tables/${tableId}/connect`);
  const conn = await connResp.json();
  if (!conn.accessToken) {
    log("Unable to connect", conn);
    return;
  }
  const socket = io(conn.socketUrl, {
    auth: { token: conn.accessToken, lastEventSeq: state.lastEventSeq },
    transports: ["websocket", "polling"],
  });

  socket.on("connect", () => log("Connected to table-server", { tableId }));
  socket.on("disconnect", () => log("Disconnected"));

  socket.on("state_sync", (payload) => {
    const snapshot = payload.snapshot || [];
    for (const obj of snapshot) upsertObject(obj);
    for (const event of payload.events || []) applyEvent(event);
    renderPresence(payload.presence || []);
    state.lastEventSeq = payload.lastEventSeq || state.lastEventSeq;
    log("State synchronized", { events: (payload.events || []).length });
  });

  socket.on("presence_update", (payload) => renderPresence(payload.presence || []));
  socket.on("state_event", (event) => applyEvent(event));
  socket.on("operation_ack", (ack) => {
    if (!ack.ok) log("Operation failed", ack);
    if (ack.event) applyEvent(ack.event);
    if (ack.clientOpId) state.pendingClientOps.delete(ack.clientOpId);
  });

  function sendOperation(type, payload) {
    const clientOpId = `${Date.now()}-${Math.random()}`;
    state.pendingClientOps.add(clientOpId);
    socket.emit("operation", { type, payload, clientOpId });
  }

  document.getElementById("print-card").addEventListener("click", () => {
    const sourceId = `card-${Math.floor(Math.random() * 1000)}`;
    sendOperation("print_object", {
      source: { type: "card", id: sourceId },
      metadata: { label: sourceId },
      position: { x: 20 + Math.random() * 400, y: 20 + Math.random() * 250 },
    });
  });
  document.getElementById("flip-selected").addEventListener("click", () => {
    if (!state.selectedObjectId) return;
    sendOperation("flip", { objectId: state.selectedObjectId });
  });
  document.getElementById("rotate-selected").addEventListener("click", () => {
    if (!state.selectedObjectId) return;
    const obj = state.objects.get(state.selectedObjectId);
    if (!obj) return;
    sendOperation("rotate", { objectId: obj.id, rotation: (obj.rotation + 90) % 360 });
  });
  document.getElementById("bring-front").addEventListener("click", () => {
    if (!state.selectedObjectId) return;
    let maxZ = 0;
    for (const obj of state.objects.values()) maxZ = Math.max(maxZ, obj.zIndex);
    sendOperation("set_z", { objectId: state.selectedObjectId, zIndex: maxZ + 1 });
  });
  document.getElementById("stack-selected").addEventListener("click", () => {
    if (!state.selectedObjectId) return;
    const stackId = prompt("Stack id", "stack-1");
    if (!stackId) return;
    sendOperation("stack", { objectId: state.selectedObjectId, stackId, stackOrder: 0 });
  });
})();
