CREATE CONSTRAINT panel_identity IF NOT EXISTS
FOR (n:Panel) REQUIRE (n.owner, n.id) IS UNIQUE;
CREATE CONSTRAINT circuit_identity IF NOT EXISTS
FOR (n:Circuit) REQUIRE (n.owner, n.id) IS UNIQUE;
CREATE CONSTRAINT breaker_identity IF NOT EXISTS
FOR (n:SmartBreaker) REQUIRE (n.owner, n.id) IS UNIQUE;
CREATE CONSTRAINT room_identity IF NOT EXISTS
FOR (n:Room) REQUIRE (n.owner, n.id) IS UNIQUE;
