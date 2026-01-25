// Bathroom Design Tool - 3D Application
// Using Three.js for 3D rendering

// Shape Editor Class for 2D floor plan editing
class ShapeEditor {
    constructor(canvas, onChange) {
        this.canvas = canvas;
        this.ctx = canvas.getContext('2d');
        this.onChange = onChange;

        // Points in meters (will be scaled for display)
        this.points = [];
        this.scale = 40; // pixels per meter
        this.offsetX = 120;
        this.offsetY = 100;

        // Interaction state
        this.selectedPoint = -1;
        this.isDragging = false;
        this.hoverPoint = -1;

        // Set default rectangle shape
        this.setPresetShape('rectangle');

        this.setupEvents();
    }

    setupEvents() {
        this.canvas.addEventListener('mousedown', (e) => this.onMouseDown(e));
        this.canvas.addEventListener('mousemove', (e) => this.onMouseMove(e));
        this.canvas.addEventListener('mouseup', (e) => this.onMouseUp(e));
        this.canvas.addEventListener('contextmenu', (e) => {
            e.preventDefault();
            this.onRightClick(e);
        });
        this.canvas.addEventListener('dblclick', (e) => this.onDoubleClick(e));
    }

    getMousePos(e) {
        const rect = this.canvas.getBoundingClientRect();
        return {
            x: (e.clientX - rect.left - this.offsetX) / this.scale,
            y: (e.clientY - rect.top - this.offsetY) / this.scale
        };
    }

    findPointAt(pos, threshold = 0.2) {
        for (let i = 0; i < this.points.length; i++) {
            const dx = this.points[i].x - pos.x;
            const dy = this.points[i].y - pos.y;
            if (Math.sqrt(dx * dx + dy * dy) < threshold) {
                return i;
            }
        }
        return -1;
    }

    findEdgeAt(pos, threshold = 0.15) {
        for (let i = 0; i < this.points.length; i++) {
            const p1 = this.points[i];
            const p2 = this.points[(i + 1) % this.points.length];

            // Distance from point to line segment
            const dist = this.pointToSegmentDistance(pos, p1, p2);
            if (dist < threshold) {
                return i;
            }
        }
        return -1;
    }

    pointToSegmentDistance(p, a, b) {
        const dx = b.x - a.x;
        const dy = b.y - a.y;
        const len2 = dx * dx + dy * dy;

        if (len2 === 0) return Math.sqrt((p.x - a.x) ** 2 + (p.y - a.y) ** 2);

        let t = ((p.x - a.x) * dx + (p.y - a.y) * dy) / len2;
        t = Math.max(0, Math.min(1, t));

        const projX = a.x + t * dx;
        const projY = a.y + t * dy;

        return Math.sqrt((p.x - projX) ** 2 + (p.y - projY) ** 2);
    }

    onMouseDown(e) {
        const pos = this.getMousePos(e);

        if (e.button === 0) { // Left click
            const pointIndex = this.findPointAt(pos);

            if (pointIndex >= 0) {
                this.selectedPoint = pointIndex;
                this.isDragging = true;
            }
        }
    }

    onMouseMove(e) {
        const pos = this.getMousePos(e);

        if (this.isDragging && this.selectedPoint >= 0) {
            // Snap to grid (0.1m)
            this.points[this.selectedPoint].x = Math.round(pos.x * 10) / 10;
            this.points[this.selectedPoint].y = Math.round(pos.y * 10) / 10;
            this.draw();
            this.onChange(this.points);
        } else {
            // Update hover state
            const newHover = this.findPointAt(pos);
            if (newHover !== this.hoverPoint) {
                this.hoverPoint = newHover;
                this.draw();
            }
        }
    }

    onMouseUp(e) {
        this.isDragging = false;
        this.selectedPoint = -1;
    }

    onRightClick(e) {
        const pos = this.getMousePos(e);
        const pointIndex = this.findPointAt(pos);

        // Delete point if we have more than 3
        if (pointIndex >= 0 && this.points.length > 3) {
            this.points.splice(pointIndex, 1);
            this.draw();
            this.onChange(this.points);
        }
    }

    onDoubleClick(e) {
        const pos = this.getMousePos(e);

        // Check if clicking on an edge to add a point
        const edgeIndex = this.findEdgeAt(pos);

        if (edgeIndex >= 0) {
            // Insert point on edge
            const newPoint = { x: Math.round(pos.x * 10) / 10, y: Math.round(pos.y * 10) / 10 };
            this.points.splice(edgeIndex + 1, 0, newPoint);
            this.draw();
            this.onChange(this.points);
        }
    }

    setPresetShape(shape) {
        switch (shape) {
            case 'rectangle':
                this.points = [
                    { x: -1.5, y: -1.25 },
                    { x: 1.5, y: -1.25 },
                    { x: 1.5, y: 1.25 },
                    { x: -1.5, y: 1.25 }
                ];
                break;
            case 'l-shape':
                this.points = [
                    { x: -1.5, y: -1.5 },
                    { x: 0.5, y: -1.5 },
                    { x: 0.5, y: 0 },
                    { x: 1.5, y: 0 },
                    { x: 1.5, y: 1.5 },
                    { x: -1.5, y: 1.5 }
                ];
                break;
            case 't-shape':
                this.points = [
                    { x: -0.5, y: -1.5 },
                    { x: 0.5, y: -1.5 },
                    { x: 0.5, y: -0.5 },
                    { x: 1.5, y: -0.5 },
                    { x: 1.5, y: 0.5 },
                    { x: 0.5, y: 0.5 },
                    { x: 0.5, y: 1.5 },
                    { x: -0.5, y: 1.5 },
                    { x: -0.5, y: 0.5 },
                    { x: -1.5, y: 0.5 },
                    { x: -1.5, y: -0.5 },
                    { x: -0.5, y: -0.5 }
                ];
                break;
            case 'custom':
                // Pentagon as starting custom shape
                this.points = [
                    { x: 0, y: -1.5 },
                    { x: 1.4, y: -0.5 },
                    { x: 0.9, y: 1.2 },
                    { x: -0.9, y: 1.2 },
                    { x: -1.4, y: -0.5 }
                ];
                break;
        }
        this.draw();
        this.onChange(this.points);
    }

    setPoints(points) {
        this.points = points.map(p => ({ x: p.x, y: p.y }));
        this.draw();
    }

    getPoints() {
        return this.points.map(p => ({ x: p.x, y: p.y }));
    }

    calculateArea() {
        // Shoelace formula
        let area = 0;
        const n = this.points.length;
        for (let i = 0; i < n; i++) {
            const j = (i + 1) % n;
            area += this.points[i].x * this.points[j].y;
            area -= this.points[j].x * this.points[i].y;
        }
        return Math.abs(area / 2);
    }

    draw() {
        const ctx = this.ctx;
        const w = this.canvas.width;
        const h = this.canvas.height;

        // Clear
        ctx.fillStyle = '#1e272e';
        ctx.fillRect(0, 0, w, h);

        // Draw grid
        ctx.strokeStyle = '#3d4852';
        ctx.lineWidth = 1;

        for (let x = -3; x <= 3; x += 0.5) {
            const px = this.offsetX + x * this.scale;
            ctx.beginPath();
            ctx.moveTo(px, 0);
            ctx.lineTo(px, h);
            ctx.stroke();
        }

        for (let y = -2.5; y <= 2.5; y += 0.5) {
            const py = this.offsetY + y * this.scale;
            ctx.beginPath();
            ctx.moveTo(0, py);
            ctx.lineTo(w, py);
            ctx.stroke();
        }

        // Draw meter marks
        ctx.fillStyle = '#6b7280';
        ctx.font = '10px sans-serif';
        ctx.textAlign = 'center';

        for (let x = -2; x <= 2; x++) {
            const px = this.offsetX + x * this.scale;
            ctx.fillText(`${x}m`, px, h - 5);
        }

        // Draw shape
        if (this.points.length >= 3) {
            // Fill
            ctx.beginPath();
            ctx.moveTo(
                this.offsetX + this.points[0].x * this.scale,
                this.offsetY + this.points[0].y * this.scale
            );
            for (let i = 1; i < this.points.length; i++) {
                ctx.lineTo(
                    this.offsetX + this.points[i].x * this.scale,
                    this.offsetY + this.points[i].y * this.scale
                );
            }
            ctx.closePath();
            ctx.fillStyle = 'rgba(52, 152, 219, 0.2)';
            ctx.fill();

            // Stroke
            ctx.strokeStyle = '#3498db';
            ctx.lineWidth = 2;
            ctx.stroke();

            // Draw points
            for (let i = 0; i < this.points.length; i++) {
                const px = this.offsetX + this.points[i].x * this.scale;
                const py = this.offsetY + this.points[i].y * this.scale;

                ctx.beginPath();
                ctx.arc(px, py, i === this.hoverPoint ? 8 : 6, 0, Math.PI * 2);
                ctx.fillStyle = i === this.hoverPoint ? '#e74c3c' : '#3498db';
                ctx.fill();
                ctx.strokeStyle = '#fff';
                ctx.lineWidth = 2;
                ctx.stroke();
            }

            // Draw dimensions on edges
            ctx.fillStyle = '#9ca3af';
            ctx.font = '9px sans-serif';

            for (let i = 0; i < this.points.length; i++) {
                const p1 = this.points[i];
                const p2 = this.points[(i + 1) % this.points.length];
                const midX = this.offsetX + (p1.x + p2.x) / 2 * this.scale;
                const midY = this.offsetY + (p1.y + p2.y) / 2 * this.scale;
                const length = Math.sqrt((p2.x - p1.x) ** 2 + (p2.y - p1.y) ** 2);

                if (length > 0.3) {
                    ctx.fillText(`${length.toFixed(1)}m`, midX, midY - 8);
                }
            }
        }
    }
}

class BathroomDesigner {
    constructor() {
        this.scene = null;
        this.camera = null;
        this.renderer = null;
        this.controls = null;
        this.raycaster = new THREE.Raycaster();
        this.mouse = new THREE.Vector2();

        // Room properties
        this.roomHeight = 2.4;
        this.roomScale = 1;
        this.wallColor = 0xe8e4e0;
        this.floorColor = 0x8b7355;

        // Room shape (polygon points)
        this.roomShape = [];
        this.shapeEditor = null;

        // Room meshes
        this.floor = null;
        this.walls = [];
        this.room = null;

        // Furniture
        this.items = [];
        this.selectedItem = null;
        this.itemIdCounter = 0;

        // Furniture definitions
        this.furnitureTypes = {
            toilet: { width: 0.4, depth: 0.65, height: 0.45, color: 0xffffff, icon: '🚽' },
            sink: { width: 0.5, depth: 0.45, height: 0.85, color: 0xffffff, icon: '🚰' },
            bathtub: { width: 0.75, depth: 1.7, height: 0.55, color: 0xffffff, icon: '🛁' },
            shower: { width: 0.9, depth: 0.9, height: 2.0, color: 0xaaddff, icon: '🚿' },
            mirror: { width: 0.6, depth: 0.05, height: 0.8, color: 0xc0c0c0, icon: '🪞', wallMounted: true },
            cabinet: { width: 0.6, depth: 0.35, height: 0.7, color: 0x8b4513, icon: '🗄️' },
            towelrack: { width: 0.6, depth: 0.1, height: 0.05, color: 0xc0c0c0, icon: '🧺', wallMounted: true },
            plant: { width: 0.3, depth: 0.3, height: 0.5, color: 0x228b22, icon: '🪴' }
        };

        // Drag state
        this.isDragging = false;
        this.dragPlane = new THREE.Plane(new THREE.Vector3(0, 1, 0), 0);
        this.dragOffset = new THREE.Vector3();

        // Camera orbit state
        this.isOrbiting = false;
        this.orbitStart = { x: 0, y: 0 };
        this.cameraTheta = Math.PI / 4;
        this.cameraPhi = Math.PI / 4;
        this.cameraRadius = 6;
        this.cameraTarget = new THREE.Vector3(0, 1, 0);

        this.init();
    }

    init() {
        this.createScene();
        this.createLights();
        this.setupShapeEditor();
        this.createRoom();
        this.setupEventListeners();
        this.setupControls();
        this.animate();

        // Hide loading
        document.getElementById('loading').classList.add('hidden');
    }

    setupShapeEditor() {
        const canvas = document.getElementById('shape-editor');
        this.shapeEditor = new ShapeEditor(canvas, (points) => {
            this.roomShape = points;
            this.createRoom();
            this.updateRoomSizeDisplay();
        });
        this.roomShape = this.shapeEditor.getPoints();
    }

    createScene() {
        const container = document.getElementById('canvas-container');
        const width = container.clientWidth;
        const height = container.clientHeight;

        // Scene
        this.scene = new THREE.Scene();
        this.scene.background = new THREE.Color(0x1a1a2e);

        // Camera
        this.camera = new THREE.PerspectiveCamera(60, width / height, 0.1, 100);
        this.updateCameraPosition();

        // Renderer
        this.renderer = new THREE.WebGLRenderer({ antialias: true });
        this.renderer.setSize(width, height);
        this.renderer.setPixelRatio(window.devicePixelRatio);
        this.renderer.shadowMap.enabled = true;
        this.renderer.shadowMap.type = THREE.PCFSoftShadowMap;
        container.appendChild(this.renderer.domElement);
    }

    createLights() {
        // Ambient light
        const ambient = new THREE.AmbientLight(0xffffff, 0.5);
        this.scene.add(ambient);

        // Main directional light
        const mainLight = new THREE.DirectionalLight(0xffffff, 0.8);
        mainLight.position.set(5, 10, 5);
        mainLight.castShadow = true;
        mainLight.shadow.mapSize.width = 2048;
        mainLight.shadow.mapSize.height = 2048;
        mainLight.shadow.camera.near = 0.5;
        mainLight.shadow.camera.far = 50;
        mainLight.shadow.camera.left = -10;
        mainLight.shadow.camera.right = 10;
        mainLight.shadow.camera.top = 10;
        mainLight.shadow.camera.bottom = -10;
        this.scene.add(mainLight);

        // Fill light
        const fillLight = new THREE.DirectionalLight(0xffffff, 0.3);
        fillLight.position.set(-5, 5, -5);
        this.scene.add(fillLight);

        // Point light (ceiling)
        const ceilingLight = new THREE.PointLight(0xffffee, 0.5, 10);
        ceilingLight.position.set(0, this.roomHeight - 0.1, 0);
        this.scene.add(ceilingLight);
    }

    createRoom() {
        // Remove existing room
        if (this.room) {
            this.scene.remove(this.room);
        }

        this.room = new THREE.Group();

        if (this.roomShape.length < 3) return;

        const scale = this.roomScale;
        const scaledPoints = this.roomShape.map(p => ({
            x: p.x * scale,
            y: p.y * scale
        }));

        // Create floor using Shape
        const floorShape = new THREE.Shape();
        floorShape.moveTo(scaledPoints[0].x, scaledPoints[0].y);
        for (let i = 1; i < scaledPoints.length; i++) {
            floorShape.lineTo(scaledPoints[i].x, scaledPoints[i].y);
        }
        floorShape.closePath();

        const floorGeometry = new THREE.ShapeGeometry(floorShape);
        const floorMaterial = new THREE.MeshStandardMaterial({
            color: this.floorColor,
            roughness: 0.8,
            metalness: 0.1
        });
        this.floor = new THREE.Mesh(floorGeometry, floorMaterial);
        this.floor.rotation.x = -Math.PI / 2;
        this.floor.position.y = 0;
        this.floor.receiveShadow = true;
        this.room.add(this.floor);

        // Add floor grid
        const bounds = this.getShapeBounds(scaledPoints);
        const gridSize = Math.max(bounds.width, bounds.height) + 2;
        const gridHelper = new THREE.GridHelper(gridSize, gridSize * 2, 0x444444, 0x333333);
        gridHelper.position.y = 0.001;
        gridHelper.position.x = bounds.centerX;
        gridHelper.position.z = bounds.centerY;
        this.room.add(gridHelper);

        // Create walls
        const wallMaterial = new THREE.MeshStandardMaterial({
            color: this.wallColor,
            roughness: 0.9,
            metalness: 0,
            side: THREE.DoubleSide
        });

        for (let i = 0; i < scaledPoints.length; i++) {
            const p1 = scaledPoints[i];
            const p2 = scaledPoints[(i + 1) % scaledPoints.length];

            const dx = p2.x - p1.x;
            const dy = p2.y - p1.y;
            const length = Math.sqrt(dx * dx + dy * dy);
            const angle = Math.atan2(dy, dx);

            const wallGeometry = new THREE.PlaneGeometry(length, this.roomHeight);
            const wall = new THREE.Mesh(wallGeometry, wallMaterial.clone());

            // Position at midpoint of edge
            wall.position.x = (p1.x + p2.x) / 2;
            wall.position.z = (p1.y + p2.y) / 2;
            wall.position.y = this.roomHeight / 2;

            // Rotate to face inward
            wall.rotation.y = -angle + Math.PI / 2;

            wall.receiveShadow = true;
            wall.castShadow = true;
            this.room.add(wall);
        }

        this.scene.add(this.room);
    }

    getShapeBounds(points) {
        let minX = Infinity, maxX = -Infinity;
        let minY = Infinity, maxY = -Infinity;

        for (const p of points) {
            minX = Math.min(minX, p.x);
            maxX = Math.max(maxX, p.x);
            minY = Math.min(minY, p.y);
            maxY = Math.max(maxY, p.y);
        }

        return {
            minX, maxX, minY, maxY,
            width: maxX - minX,
            height: maxY - minY,
            centerX: (minX + maxX) / 2,
            centerY: (minY + maxY) / 2
        };
    }

    isPointInRoom(x, z) {
        // Ray casting algorithm for point in polygon
        const scale = this.roomScale;
        const scaledPoints = this.roomShape.map(p => ({
            x: p.x * scale,
            y: p.y * scale
        }));

        let inside = false;
        for (let i = 0, j = scaledPoints.length - 1; i < scaledPoints.length; j = i++) {
            const xi = scaledPoints[i].x, yi = scaledPoints[i].y;
            const xj = scaledPoints[j].x, yj = scaledPoints[j].y;

            if (((yi > z) !== (yj > z)) && (x < (xj - xi) * (z - yi) / (yj - yi) + xi)) {
                inside = !inside;
            }
        }
        return inside;
    }

    createFurniture(type, position = null) {
        const config = this.furnitureTypes[type];
        if (!config) return null;

        const group = new THREE.Group();
        group.userData = {
            id: this.itemIdCounter++,
            type: type,
            width: config.width,
            depth: config.depth,
            height: config.height,
            color: config.color,
            icon: config.icon,
            wallMounted: config.wallMounted || false
        };

        // Create based on type
        switch(type) {
            case 'toilet':
                this.createToilet(group, config);
                break;
            case 'sink':
                this.createSink(group, config);
                break;
            case 'bathtub':
                this.createBathtub(group, config);
                break;
            case 'shower':
                this.createShower(group, config);
                break;
            case 'mirror':
                this.createMirror(group, config);
                break;
            case 'cabinet':
                this.createCabinet(group, config);
                break;
            case 'towelrack':
                this.createTowelRack(group, config);
                break;
            case 'plant':
                this.createPlant(group, config);
                break;
            default:
                this.createGenericBox(group, config);
        }

        // Position
        if (position) {
            group.position.copy(position);
        } else {
            // Default position in center
            group.position.set(0, 0, 0);
            if (config.wallMounted) {
                group.position.y = 1.4;
            }
        }

        this.scene.add(group);
        this.items.push(group);
        this.updateItemsList();
        this.updateItemCount();

        return group;
    }

    createToilet(group, config) {
        // Base
        const baseGeometry = new THREE.BoxGeometry(config.width, config.height * 0.6, config.depth * 0.7);
        const material = new THREE.MeshStandardMaterial({ color: config.color, roughness: 0.3 });
        const base = new THREE.Mesh(baseGeometry, material);
        base.position.y = config.height * 0.3;
        base.castShadow = true;
        group.add(base);

        // Bowl
        const bowlGeometry = new THREE.CylinderGeometry(config.width * 0.4, config.width * 0.35, config.height * 0.3, 16);
        const bowl = new THREE.Mesh(bowlGeometry, material);
        bowl.position.set(0, config.height * 0.4, config.depth * 0.15);
        bowl.castShadow = true;
        group.add(bowl);

        // Tank
        const tankGeometry = new THREE.BoxGeometry(config.width * 0.9, config.height * 0.5, config.depth * 0.25);
        const tank = new THREE.Mesh(tankGeometry, material);
        tank.position.set(0, config.height * 0.65, -config.depth * 0.2);
        tank.castShadow = true;
        group.add(tank);

        // Seat
        const seatGeometry = new THREE.TorusGeometry(config.width * 0.35, 0.03, 8, 24, Math.PI);
        const seat = new THREE.Mesh(seatGeometry, material);
        seat.rotation.x = -Math.PI / 2;
        seat.position.set(0, config.height * 0.55, config.depth * 0.15);
        seat.castShadow = true;
        group.add(seat);
    }

    createSink(group, config) {
        // Pedestal
        const pedestalGeometry = new THREE.CylinderGeometry(config.width * 0.15, config.width * 0.2, config.height * 0.7, 16);
        const material = new THREE.MeshStandardMaterial({ color: config.color, roughness: 0.3 });
        const pedestal = new THREE.Mesh(pedestalGeometry, material);
        pedestal.position.y = config.height * 0.35;
        pedestal.castShadow = true;
        group.add(pedestal);

        // Basin
        const basinGeometry = new THREE.CylinderGeometry(config.width * 0.45, config.width * 0.35, config.height * 0.2, 24);
        const basin = new THREE.Mesh(basinGeometry, material);
        basin.position.y = config.height * 0.8;
        basin.castShadow = true;
        group.add(basin);

        // Faucet
        const faucetMaterial = new THREE.MeshStandardMaterial({ color: 0xc0c0c0, metalness: 0.8, roughness: 0.2 });
        const faucetBase = new THREE.CylinderGeometry(0.02, 0.02, 0.15, 8);
        const faucet = new THREE.Mesh(faucetBase, faucetMaterial);
        faucet.position.set(0, config.height * 0.95, -config.depth * 0.25);
        faucet.castShadow = true;
        group.add(faucet);

        // Faucet spout
        const spoutGeometry = new THREE.CylinderGeometry(0.015, 0.015, 0.1, 8);
        const spout = new THREE.Mesh(spoutGeometry, faucetMaterial);
        spout.rotation.x = Math.PI / 2;
        spout.position.set(0, config.height * 1.0, -config.depth * 0.15);
        spout.castShadow = true;
        group.add(spout);
    }

    createBathtub(group, config) {
        // Main tub body
        const material = new THREE.MeshStandardMaterial({ color: config.color, roughness: 0.3 });

        // Outer shell
        const outerGeometry = new THREE.BoxGeometry(config.width, config.height, config.depth);
        const outer = new THREE.Mesh(outerGeometry, material);
        outer.position.y = config.height / 2;
        outer.castShadow = true;
        group.add(outer);

        // Inner (water area) - slightly smaller and higher
        const innerMaterial = new THREE.MeshStandardMaterial({ color: 0xadd8e6, roughness: 0.1, metalness: 0.1 });
        const innerGeometry = new THREE.BoxGeometry(config.width - 0.1, config.height - 0.15, config.depth - 0.1);
        const inner = new THREE.Mesh(innerGeometry, innerMaterial);
        inner.position.y = config.height / 2 + 0.08;
        group.add(inner);

        // Faucet
        const faucetMaterial = new THREE.MeshStandardMaterial({ color: 0xc0c0c0, metalness: 0.8, roughness: 0.2 });
        const faucetGeometry = new THREE.CylinderGeometry(0.03, 0.03, 0.2, 8);
        const faucet = new THREE.Mesh(faucetGeometry, faucetMaterial);
        faucet.position.set(0, config.height + 0.1, -config.depth / 2 + 0.15);
        faucet.castShadow = true;
        group.add(faucet);
    }

    createShower(group, config) {
        // Glass panels
        const glassMaterial = new THREE.MeshStandardMaterial({
            color: 0xaaddff,
            transparent: true,
            opacity: 0.3,
            roughness: 0.1,
            metalness: 0.1
        });

        // Back panel
        const backPanel = new THREE.Mesh(
            new THREE.BoxGeometry(config.width, config.height, 0.02),
            glassMaterial
        );
        backPanel.position.set(0, config.height / 2, -config.depth / 2);
        group.add(backPanel);

        // Side panel
        const sidePanel = new THREE.Mesh(
            new THREE.BoxGeometry(0.02, config.height, config.depth),
            glassMaterial
        );
        sidePanel.position.set(-config.width / 2, config.height / 2, 0);
        group.add(sidePanel);

        // Door panel
        const doorPanel = new THREE.Mesh(
            new THREE.BoxGeometry(0.02, config.height, config.depth * 0.6),
            glassMaterial
        );
        doorPanel.position.set(config.width / 2, config.height / 2, config.depth * 0.2);
        group.add(doorPanel);

        // Floor tray
        const trayMaterial = new THREE.MeshStandardMaterial({ color: 0xffffff, roughness: 0.4 });
        const tray = new THREE.Mesh(
            new THREE.BoxGeometry(config.width, 0.05, config.depth),
            trayMaterial
        );
        tray.position.y = 0.025;
        tray.receiveShadow = true;
        group.add(tray);

        // Shower head
        const metalMaterial = new THREE.MeshStandardMaterial({ color: 0xc0c0c0, metalness: 0.8, roughness: 0.2 });
        const headGeometry = new THREE.CylinderGeometry(0.08, 0.06, 0.05, 16);
        const head = new THREE.Mesh(headGeometry, metalMaterial);
        head.position.set(0, config.height - 0.15, -config.depth / 2 + 0.15);
        head.rotation.x = Math.PI / 6;
        head.castShadow = true;
        group.add(head);

        // Pipe
        const pipeGeometry = new THREE.CylinderGeometry(0.015, 0.015, 0.5, 8);
        const pipe = new THREE.Mesh(pipeGeometry, metalMaterial);
        pipe.position.set(0, config.height - 0.4, -config.depth / 2 + 0.05);
        pipe.castShadow = true;
        group.add(pipe);
    }

    createMirror(group, config) {
        // Frame
        const frameMaterial = new THREE.MeshStandardMaterial({ color: 0x8b4513, roughness: 0.7 });
        const frameGeometry = new THREE.BoxGeometry(config.width + 0.05, config.height + 0.05, 0.03);
        const frame = new THREE.Mesh(frameGeometry, frameMaterial);
        frame.castShadow = true;
        group.add(frame);

        // Mirror surface
        const mirrorMaterial = new THREE.MeshStandardMaterial({
            color: 0xc0c0c0,
            metalness: 0.9,
            roughness: 0.1
        });
        const mirrorGeometry = new THREE.BoxGeometry(config.width - 0.02, config.height - 0.02, 0.02);
        const mirror = new THREE.Mesh(mirrorGeometry, mirrorMaterial);
        mirror.position.z = 0.02;
        group.add(mirror);
    }

    createCabinet(group, config) {
        const material = new THREE.MeshStandardMaterial({ color: config.color, roughness: 0.6 });

        // Main body
        const bodyGeometry = new THREE.BoxGeometry(config.width, config.height, config.depth);
        const body = new THREE.Mesh(bodyGeometry, material);
        body.position.y = config.height / 2;
        body.castShadow = true;
        group.add(body);

        // Door line
        const lineMaterial = new THREE.MeshStandardMaterial({ color: 0x5c3317, roughness: 0.5 });
        const lineGeometry = new THREE.BoxGeometry(0.01, config.height - 0.1, config.depth + 0.01);
        const line = new THREE.Mesh(lineGeometry, lineMaterial);
        line.position.set(0, config.height / 2, config.depth / 2);
        group.add(line);

        // Handles
        const handleMaterial = new THREE.MeshStandardMaterial({ color: 0xc0c0c0, metalness: 0.8, roughness: 0.2 });
        const handleGeometry = new THREE.CylinderGeometry(0.01, 0.01, 0.08, 8);

        const leftHandle = new THREE.Mesh(handleGeometry, handleMaterial);
        leftHandle.rotation.x = Math.PI / 2;
        leftHandle.position.set(-config.width * 0.15, config.height / 2, config.depth / 2 + 0.03);
        group.add(leftHandle);

        const rightHandle = new THREE.Mesh(handleGeometry, handleMaterial);
        rightHandle.rotation.x = Math.PI / 2;
        rightHandle.position.set(config.width * 0.15, config.height / 2, config.depth / 2 + 0.03);
        group.add(rightHandle);
    }

    createTowelRack(group, config) {
        const material = new THREE.MeshStandardMaterial({ color: config.color, metalness: 0.8, roughness: 0.2 });

        // Bar
        const barGeometry = new THREE.CylinderGeometry(0.015, 0.015, config.width, 8);
        const bar = new THREE.Mesh(barGeometry, material);
        bar.rotation.z = Math.PI / 2;
        bar.castShadow = true;
        group.add(bar);

        // End caps
        const capGeometry = new THREE.SphereGeometry(0.025, 8, 8);
        const leftCap = new THREE.Mesh(capGeometry, material);
        leftCap.position.x = -config.width / 2;
        group.add(leftCap);

        const rightCap = new THREE.Mesh(capGeometry, material);
        rightCap.position.x = config.width / 2;
        group.add(rightCap);

        // Mounting brackets
        const bracketGeometry = new THREE.BoxGeometry(0.04, 0.06, 0.03);
        const leftBracket = new THREE.Mesh(bracketGeometry, material);
        leftBracket.position.set(-config.width / 2 + 0.05, 0, -0.02);
        group.add(leftBracket);

        const rightBracket = new THREE.Mesh(bracketGeometry, material);
        rightBracket.position.set(config.width / 2 - 0.05, 0, -0.02);
        group.add(rightBracket);
    }

    createPlant(group, config) {
        // Pot
        const potMaterial = new THREE.MeshStandardMaterial({ color: 0x8b4513, roughness: 0.7 });
        const potGeometry = new THREE.CylinderGeometry(config.width * 0.35, config.width * 0.25, config.height * 0.4, 16);
        const pot = new THREE.Mesh(potGeometry, potMaterial);
        pot.position.y = config.height * 0.2;
        pot.castShadow = true;
        group.add(pot);

        // Soil
        const soilMaterial = new THREE.MeshStandardMaterial({ color: 0x3d2817, roughness: 0.9 });
        const soilGeometry = new THREE.CylinderGeometry(config.width * 0.33, config.width * 0.33, 0.05, 16);
        const soil = new THREE.Mesh(soilGeometry, soilMaterial);
        soil.position.y = config.height * 0.38;
        group.add(soil);

        // Plant foliage (simplified as spheres)
        const leafMaterial = new THREE.MeshStandardMaterial({ color: config.color, roughness: 0.8 });

        const foliage1 = new THREE.Mesh(new THREE.SphereGeometry(config.width * 0.25, 8, 8), leafMaterial);
        foliage1.position.set(0, config.height * 0.65, 0);
        foliage1.castShadow = true;
        group.add(foliage1);

        const foliage2 = new THREE.Mesh(new THREE.SphereGeometry(config.width * 0.2, 8, 8), leafMaterial);
        foliage2.position.set(config.width * 0.15, config.height * 0.75, config.width * 0.1);
        foliage2.castShadow = true;
        group.add(foliage2);

        const foliage3 = new THREE.Mesh(new THREE.SphereGeometry(config.width * 0.18, 8, 8), leafMaterial);
        foliage3.position.set(-config.width * 0.12, config.height * 0.8, -config.width * 0.08);
        foliage3.castShadow = true;
        group.add(foliage3);
    }

    createGenericBox(group, config) {
        const geometry = new THREE.BoxGeometry(config.width, config.height, config.depth);
        const material = new THREE.MeshStandardMaterial({ color: config.color, roughness: 0.5 });
        const mesh = new THREE.Mesh(geometry, material);
        mesh.position.y = config.height / 2;
        mesh.castShadow = true;
        group.add(mesh);
    }

    updateCameraPosition() {
        const x = this.cameraRadius * Math.sin(this.cameraPhi) * Math.cos(this.cameraTheta);
        const y = this.cameraRadius * Math.cos(this.cameraPhi);
        const z = this.cameraRadius * Math.sin(this.cameraPhi) * Math.sin(this.cameraTheta);

        this.camera.position.set(
            this.cameraTarget.x + x,
            this.cameraTarget.y + y,
            this.cameraTarget.z + z
        );
        this.camera.lookAt(this.cameraTarget);
    }

    setupEventListeners() {
        const container = document.getElementById('canvas-container');

        // Mouse events for 3D interaction
        container.addEventListener('mousedown', (e) => this.onMouseDown(e));
        container.addEventListener('mousemove', (e) => this.onMouseMove(e));
        container.addEventListener('mouseup', (e) => this.onMouseUp(e));
        container.addEventListener('wheel', (e) => this.onWheel(e));
        container.addEventListener('contextmenu', (e) => e.preventDefault());

        // Window resize
        window.addEventListener('resize', () => this.onResize());

        // Keyboard
        window.addEventListener('keydown', (e) => this.onKeyDown(e));
    }

    setupControls() {
        // Room height control
        this.setupDimensionControl('room-height', 'room-height-slider', (val) => {
            this.roomHeight = parseFloat(val);
            this.createRoom();
            this.updateRoomSizeDisplay();
        });

        // Room scale control
        this.setupDimensionControl('room-scale', 'room-scale-slider', (val) => {
            this.roomScale = parseFloat(val);
            this.createRoom();
            this.updateRoomSizeDisplay();
        });

        // Color controls
        document.getElementById('wall-color').addEventListener('input', (e) => {
            this.wallColor = parseInt(e.target.value.replace('#', ''), 16);
            this.createRoom();
        });

        document.getElementById('floor-color').addEventListener('input', (e) => {
            this.floorColor = parseInt(e.target.value.replace('#', ''), 16);
            this.createRoom();
        });

        // View buttons
        document.querySelectorAll('.view-btn').forEach(btn => {
            btn.addEventListener('click', () => this.setView(btn.dataset.view));
        });

        // Reset camera
        document.getElementById('reset-camera').addEventListener('click', () => this.resetCamera());

        // Shape preset buttons
        document.querySelectorAll('.shape-preset-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                document.querySelectorAll('.shape-preset-btn').forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                this.shapeEditor.setPresetShape(btn.dataset.shape);
            });
        });

        // Clear shape button
        document.getElementById('clear-shape').addEventListener('click', () => {
            const activeBtn = document.querySelector('.shape-preset-btn.active');
            const shape = activeBtn ? activeBtn.dataset.shape : 'rectangle';
            this.shapeEditor.setPresetShape(shape);
        });

        // Furniture buttons
        document.querySelectorAll('.furniture-btn').forEach(btn => {
            btn.addEventListener('click', () => this.createFurniture(btn.dataset.type));
        });

        // Item property controls
        this.setupItemPropertyControls();

        // Action buttons
        document.getElementById('delete-item').addEventListener('click', () => this.deleteSelectedItem());
        document.getElementById('duplicate-item').addEventListener('click', () => this.duplicateSelectedItem());
        document.getElementById('clear-all').addEventListener('click', () => this.clearAllItems());
        document.getElementById('save-design').addEventListener('click', () => this.saveDesign());
        document.getElementById('load-design').addEventListener('click', () => this.loadDesign());
    }

    setupDimensionControl(inputId, sliderId, callback) {
        const input = document.getElementById(inputId);
        const slider = document.getElementById(sliderId);

        input.addEventListener('change', (e) => {
            slider.value = e.target.value;
            callback(e.target.value);
        });

        slider.addEventListener('input', (e) => {
            input.value = e.target.value;
            callback(e.target.value);
        });
    }

    setupItemPropertyControls() {
        // Position controls
        document.getElementById('item-pos-x').addEventListener('change', (e) => {
            if (this.selectedItem) {
                this.selectedItem.position.x = parseFloat(e.target.value);
            }
        });

        document.getElementById('item-pos-z').addEventListener('change', (e) => {
            if (this.selectedItem) {
                this.selectedItem.position.z = parseFloat(e.target.value);
            }
        });

        // Rotation
        const rotInput = document.getElementById('item-rotation');
        const rotSlider = document.getElementById('item-rotation-slider');

        rotInput.addEventListener('change', (e) => {
            if (this.selectedItem) {
                rotSlider.value = e.target.value;
                this.selectedItem.rotation.y = parseFloat(e.target.value) * Math.PI / 180;
            }
        });

        rotSlider.addEventListener('input', (e) => {
            if (this.selectedItem) {
                rotInput.value = e.target.value;
                this.selectedItem.rotation.y = parseFloat(e.target.value) * Math.PI / 180;
            }
        });

        // Size controls
        ['width', 'depth', 'height'].forEach(dim => {
            document.getElementById(`item-${dim}`).addEventListener('change', (e) => {
                if (this.selectedItem) {
                    const val = parseFloat(e.target.value);
                    this.selectedItem.userData[dim] = val;
                    this.rebuildItem(this.selectedItem);
                }
            });
        });

        // Color
        document.getElementById('item-color').addEventListener('input', (e) => {
            if (this.selectedItem) {
                const color = parseInt(e.target.value.replace('#', ''), 16);
                this.selectedItem.userData.color = color;
                this.selectedItem.traverse(child => {
                    if (child.isMesh && child.material && !child.material.metalness) {
                        child.material.color.setHex(color);
                    }
                });
            }
        });
    }

    rebuildItem(item) {
        const type = item.userData.type;
        const config = {
            width: item.userData.width,
            depth: item.userData.depth,
            height: item.userData.height,
            color: item.userData.color
        };

        // Remove children
        while(item.children.length > 0) {
            item.remove(item.children[0]);
        }

        // Rebuild
        switch(type) {
            case 'toilet': this.createToilet(item, config); break;
            case 'sink': this.createSink(item, config); break;
            case 'bathtub': this.createBathtub(item, config); break;
            case 'shower': this.createShower(item, config); break;
            case 'mirror': this.createMirror(item, config); break;
            case 'cabinet': this.createCabinet(item, config); break;
            case 'towelrack': this.createTowelRack(item, config); break;
            case 'plant': this.createPlant(item, config); break;
            default: this.createGenericBox(item, config);
        }
    }

    onMouseDown(e) {
        const rect = this.renderer.domElement.getBoundingClientRect();
        this.mouse.x = ((e.clientX - rect.left) / rect.width) * 2 - 1;
        this.mouse.y = -((e.clientY - rect.top) / rect.height) * 2 + 1;

        if (e.button === 2) {
            // Right click - orbit
            this.isOrbiting = true;
            this.orbitStart = { x: e.clientX, y: e.clientY };
        } else if (e.button === 0) {
            // Left click - select/drag
            this.raycaster.setFromCamera(this.mouse, this.camera);

            const itemMeshes = [];
            this.items.forEach(item => {
                item.traverse(child => {
                    if (child.isMesh) {
                        child.userData.parentItem = item;
                        itemMeshes.push(child);
                    }
                });
            });

            const intersects = this.raycaster.intersectObjects(itemMeshes);

            if (intersects.length > 0) {
                const item = intersects[0].object.userData.parentItem;
                this.selectItem(item);

                // Start dragging
                this.isDragging = true;
                this.dragPlane.setFromNormalAndCoplanarPoint(
                    new THREE.Vector3(0, 1, 0),
                    item.position
                );

                const intersection = new THREE.Vector3();
                this.raycaster.ray.intersectPlane(this.dragPlane, intersection);
                this.dragOffset.subVectors(item.position, intersection);
            } else {
                this.deselectItem();
            }
        }
    }

    onMouseMove(e) {
        const rect = this.renderer.domElement.getBoundingClientRect();
        this.mouse.x = ((e.clientX - rect.left) / rect.width) * 2 - 1;
        this.mouse.y = -((e.clientY - rect.top) / rect.height) * 2 + 1;

        if (this.isOrbiting) {
            const deltaX = e.clientX - this.orbitStart.x;
            const deltaY = e.clientY - this.orbitStart.y;

            this.cameraTheta -= deltaX * 0.01;
            this.cameraPhi = Math.max(0.1, Math.min(Math.PI / 2 - 0.1, this.cameraPhi - deltaY * 0.01));

            this.updateCameraPosition();

            this.orbitStart = { x: e.clientX, y: e.clientY };
        } else if (this.isDragging && this.selectedItem) {
            this.raycaster.setFromCamera(this.mouse, this.camera);

            const intersection = new THREE.Vector3();
            this.raycaster.ray.intersectPlane(this.dragPlane, intersection);

            this.selectedItem.position.x = intersection.x + this.dragOffset.x;
            this.selectedItem.position.z = intersection.z + this.dragOffset.z;

            this.updatePropertyPanel();
        }
    }

    onMouseUp(e) {
        this.isDragging = false;
        this.isOrbiting = false;
    }

    onWheel(e) {
        e.preventDefault();
        this.cameraRadius = Math.max(2, Math.min(15, this.cameraRadius + e.deltaY * 0.01));
        this.updateCameraPosition();
    }

    onKeyDown(e) {
        if (!this.selectedItem) return;

        const step = e.shiftKey ? 0.5 : 0.1;
        const rotStep = e.shiftKey ? 45 : 15;

        switch(e.key) {
            case 'ArrowLeft':
                this.selectedItem.position.x -= step;
                break;
            case 'ArrowRight':
                this.selectedItem.position.x += step;
                break;
            case 'ArrowUp':
                this.selectedItem.position.z -= step;
                break;
            case 'ArrowDown':
                this.selectedItem.position.z += step;
                break;
            case 'r':
            case 'R':
                this.selectedItem.rotation.y += rotStep * Math.PI / 180;
                break;
            case 'Delete':
            case 'Backspace':
                this.deleteSelectedItem();
                break;
        }

        this.updatePropertyPanel();
    }

    onResize() {
        const container = document.getElementById('canvas-container');
        const width = container.clientWidth;
        const height = container.clientHeight;

        this.camera.aspect = width / height;
        this.camera.updateProjectionMatrix();
        this.renderer.setSize(width, height);
    }

    selectItem(item) {
        this.deselectItem();
        this.selectedItem = item;

        // Highlight
        item.traverse(child => {
            if (child.isMesh) {
                child.userData.originalMaterial = child.material;
                child.material = child.material.clone();
                child.material.emissive = new THREE.Color(0x3498db);
                child.material.emissiveIntensity = 0.3;
            }
        });

        this.showPropertyPanel();
        this.updatePropertyPanel();
        this.updateItemsList();
    }

    deselectItem() {
        if (this.selectedItem) {
            this.selectedItem.traverse(child => {
                if (child.isMesh && child.userData.originalMaterial) {
                    child.material = child.userData.originalMaterial;
                }
            });
            this.selectedItem = null;
        }

        this.hidePropertyPanel();
        this.updateItemsList();
    }

    showPropertyPanel() {
        document.getElementById('item-properties').style.display = 'block';
    }

    hidePropertyPanel() {
        document.getElementById('item-properties').style.display = 'none';
    }

    updatePropertyPanel() {
        if (!this.selectedItem) return;

        const data = this.selectedItem.userData;

        document.getElementById('selected-type').textContent = data.type;
        document.getElementById('item-pos-x').value = this.selectedItem.position.x.toFixed(2);
        document.getElementById('item-pos-z').value = this.selectedItem.position.z.toFixed(2);
        document.getElementById('item-rotation').value = Math.round(this.selectedItem.rotation.y * 180 / Math.PI);
        document.getElementById('item-rotation-slider').value = Math.round(this.selectedItem.rotation.y * 180 / Math.PI);
        document.getElementById('item-width').value = data.width;
        document.getElementById('item-depth').value = data.depth;
        document.getElementById('item-height').value = data.height;
        document.getElementById('item-color').value = '#' + data.color.toString(16).padStart(6, '0');
    }

    deleteSelectedItem() {
        if (!this.selectedItem) return;

        const index = this.items.indexOf(this.selectedItem);
        if (index > -1) {
            this.items.splice(index, 1);
        }

        this.scene.remove(this.selectedItem);
        this.selectedItem = null;
        this.hidePropertyPanel();
        this.updateItemsList();
        this.updateItemCount();
    }

    duplicateSelectedItem() {
        if (!this.selectedItem) return;

        const data = this.selectedItem.userData;
        const newItem = this.createFurniture(data.type);

        if (newItem) {
            newItem.position.copy(this.selectedItem.position);
            newItem.position.x += 0.5;
            newItem.position.z += 0.5;
            newItem.rotation.copy(this.selectedItem.rotation);
            newItem.userData.width = data.width;
            newItem.userData.depth = data.depth;
            newItem.userData.height = data.height;
            newItem.userData.color = data.color;

            this.rebuildItem(newItem);
            this.selectItem(newItem);
        }
    }

    clearAllItems() {
        if (!confirm('Clear all items from the bathroom?')) return;

        this.items.forEach(item => this.scene.remove(item));
        this.items = [];
        this.selectedItem = null;
        this.hidePropertyPanel();
        this.updateItemsList();
        this.updateItemCount();
    }

    setView(view) {
        document.querySelectorAll('.view-btn').forEach(btn => btn.classList.remove('active'));
        document.querySelector(`[data-view="${view}"]`).classList.add('active');

        switch(view) {
            case 'perspective':
                this.cameraTheta = Math.PI / 4;
                this.cameraPhi = Math.PI / 4;
                this.cameraRadius = 6;
                break;
            case 'top':
                this.cameraTheta = 0;
                this.cameraPhi = 0.01;
                this.cameraRadius = 6;
                break;
            case 'front':
                this.cameraTheta = 0;
                this.cameraPhi = Math.PI / 2 - 0.01;
                this.cameraRadius = 6;
                break;
            case 'side':
                this.cameraTheta = Math.PI / 2;
                this.cameraPhi = Math.PI / 2 - 0.01;
                this.cameraRadius = 6;
                break;
        }

        this.updateCameraPosition();
    }

    resetCamera() {
        this.cameraTheta = Math.PI / 4;
        this.cameraPhi = Math.PI / 4;
        this.cameraRadius = 6;
        this.cameraTarget.set(0, 1, 0);
        this.updateCameraPosition();

        document.querySelectorAll('.view-btn').forEach(btn => btn.classList.remove('active'));
        document.querySelector('[data-view="perspective"]').classList.add('active');
    }

    updateRoomSizeDisplay() {
        const area = this.shapeEditor.calculateArea() * this.roomScale * this.roomScale;
        document.getElementById('room-size-display').textContent =
            `Height: ${this.roomHeight.toFixed(1)}m | Area: ${area.toFixed(1)} m²`;
        document.getElementById('room-area-display').textContent = `Area: ${area.toFixed(1)} m²`;
    }

    updateItemCount() {
        document.getElementById('item-count').textContent = `Items: ${this.items.length}`;
    }

    updateItemsList() {
        const container = document.getElementById('items-list');

        if (this.items.length === 0) {
            container.innerHTML = '<p class="empty-state">No items added yet</p>';
            return;
        }

        container.innerHTML = this.items.map(item => {
            const data = item.userData;
            const isSelected = item === this.selectedItem;
            return `
                <div class="item-entry ${isSelected ? 'selected' : ''}" data-id="${data.id}">
                    <div class="item-entry-name">
                        <span class="item-entry-icon">${data.icon}</span>
                        <span>${data.type}</span>
                    </div>
                    <button class="item-entry-delete" data-id="${data.id}">×</button>
                </div>
            `;
        }).join('');

        // Add click handlers
        container.querySelectorAll('.item-entry').forEach(entry => {
            entry.addEventListener('click', (e) => {
                if (e.target.classList.contains('item-entry-delete')) {
                    const id = parseInt(e.target.dataset.id);
                    this.deleteItemById(id);
                } else {
                    const id = parseInt(entry.dataset.id);
                    const item = this.items.find(i => i.userData.id === id);
                    if (item) this.selectItem(item);
                }
            });
        });
    }

    deleteItemById(id) {
        const item = this.items.find(i => i.userData.id === id);
        if (item) {
            if (item === this.selectedItem) {
                this.selectedItem = null;
                this.hidePropertyPanel();
            }

            const index = this.items.indexOf(item);
            this.items.splice(index, 1);
            this.scene.remove(item);
            this.updateItemsList();
            this.updateItemCount();
        }
    }

    saveDesign() {
        const design = {
            room: {
                shape: this.roomShape,
                height: this.roomHeight,
                scale: this.roomScale,
                wallColor: this.wallColor,
                floorColor: this.floorColor
            },
            items: this.items.map(item => ({
                type: item.userData.type,
                position: { x: item.position.x, y: item.position.y, z: item.position.z },
                rotation: item.rotation.y,
                width: item.userData.width,
                depth: item.userData.depth,
                height: item.userData.height,
                color: item.userData.color
            }))
        };

        const json = JSON.stringify(design, null, 2);
        const blob = new Blob([json], { type: 'application/json' });
        const url = URL.createObjectURL(blob);

        const a = document.createElement('a');
        a.href = url;
        a.download = 'bathroom-design.json';
        a.click();

        URL.revokeObjectURL(url);
        this.showNotification('Design saved!', 'success');
    }

    loadDesign() {
        const input = document.createElement('input');
        input.type = 'file';
        input.accept = '.json';

        input.onchange = (e) => {
            const file = e.target.files[0];
            if (!file) return;

            const reader = new FileReader();
            reader.onload = (event) => {
                try {
                    const design = JSON.parse(event.target.result);
                    this.applyDesign(design);
                    this.showNotification('Design loaded!', 'success');
                } catch (err) {
                    this.showNotification('Failed to load design', 'error');
                }
            };
            reader.readAsText(file);
        };

        input.click();
    }

    applyDesign(design) {
        // Clear existing
        this.items.forEach(item => this.scene.remove(item));
        this.items = [];
        this.selectedItem = null;

        // Apply room settings
        if (design.room) {
            this.roomHeight = design.room.height || 2.4;
            this.roomScale = design.room.scale || 1;
            this.wallColor = design.room.wallColor || 0xe8e4e0;
            this.floorColor = design.room.floorColor || 0x8b7355;

            if (design.room.shape) {
                this.roomShape = design.room.shape;
                this.shapeEditor.setPoints(design.room.shape);
            }

            // Update controls
            document.getElementById('room-height').value = this.roomHeight;
            document.getElementById('room-height-slider').value = this.roomHeight;
            document.getElementById('room-scale').value = this.roomScale;
            document.getElementById('room-scale-slider').value = this.roomScale;
            document.getElementById('wall-color').value = '#' + this.wallColor.toString(16).padStart(6, '0');
            document.getElementById('floor-color').value = '#' + this.floorColor.toString(16).padStart(6, '0');

            this.createRoom();
            this.updateRoomSizeDisplay();
        }

        // Add items
        if (design.items) {
            design.items.forEach(itemData => {
                const item = this.createFurniture(itemData.type);
                if (item) {
                    item.position.set(itemData.position.x, itemData.position.y, itemData.position.z);
                    item.rotation.y = itemData.rotation;
                    item.userData.width = itemData.width;
                    item.userData.depth = itemData.depth;
                    item.userData.height = itemData.height;
                    item.userData.color = itemData.color;
                    this.rebuildItem(item);
                }
            });
        }

        this.updateItemsList();
        this.updateItemCount();
    }

    showNotification(message, type = 'info') {
        const existing = document.querySelector('.notification');
        if (existing) existing.remove();

        const notification = document.createElement('div');
        notification.className = `notification ${type}`;
        notification.innerHTML = `<p>${message}</p>`;
        document.body.appendChild(notification);

        setTimeout(() => notification.classList.add('show'), 10);
        setTimeout(() => {
            notification.classList.remove('show');
            setTimeout(() => notification.remove(), 300);
        }, 3000);
    }

    animate() {
        requestAnimationFrame(() => this.animate());
        this.renderer.render(this.scene, this.camera);
    }
}

// Initialize on DOM load
document.addEventListener('DOMContentLoaded', () => {
    window.bathroomDesigner = new BathroomDesigner();
});
