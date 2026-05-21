"use strict";
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
const express_1 = __importDefault(require("express"));
const cors_1 = __importDefault(require("cors"));
const dotenv_1 = __importDefault(require("dotenv"));
dotenv_1.default.config();
const app = (0, express_1.default)();
const port = process.env.PORT || 8080;
app.use((0, cors_1.default)());
app.use(express_1.default.json());
app.get('/health', (req, res) => {
    res.json({ status: 'ok', service: 'mintry-sync-api' });
});
// Endpoint for receiving WAL syncs from Enforcement Planes
app.post('/api/v1/sync', (req, res) => {
    const { mandate_id, spend, tokens } = req.body;
    if (!mandate_id) {
        return res.status(400).json({ error: 'mandate_id is required' });
    }
    // TODO: Insert into central Postgres Database
    console.log(`Received sync for mandate ${mandate_id}: $${spend} (${tokens} tokens)`);
    res.json({ status: 'synced', mandate_id });
});
app.listen(port, () => {
    console.log(`Mintry Sync API (Control Plane) running on port ${port}`);
});
