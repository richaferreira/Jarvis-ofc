// Dados fictícios: cadastrar relações reais exige levantamento da instalação.
// Não é dimensionamento, diagrama de ligação ou comprovação da função de proteção.
MERGE (panel:Panel {owner: 'casa01', id: 'qd01'})
SET panel.name = 'Quadro principal'
MERGE (circuit:Circuit {owner: 'casa01', id: 'circuit_c03'})
SET circuit.name = 'Iluminação da sala'
MERGE (device:SmartBreaker {owner: 'casa01', id: 'tuya_qd01_c03'})
SET device.vendor = 'Tuya-compatible', device.transport = 'wifi',
    device.entity_id = 'switch.disjuntor_sala', device.protection_verified = false,
    device.state_topic = 'jarvis/casa01/devices/tuya_qd01_c03/state'
MERGE (room:Room {owner: 'casa01', id: 'room_sala'})
SET room.name = 'Sala'
MERGE (panel)-[:HAS_CIRCUIT]->(circuit)
MERGE (panel)-[:HOUSES]->(device)
MERGE (circuit)-[:MONITORED_BY]->(device)
MERGE (circuit)-[:SUPPLIES]->(room);
