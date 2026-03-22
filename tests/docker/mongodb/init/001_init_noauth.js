// MongoDB Init - NO AUTH version for tests
db = db.getSiblingDB('hydra_test_db');

print('📦 Seeding users_flat...');
db.users_flat.insertMany([
  {user_id:1,email:"alice@example.com",name:"Alice Dupont",age:30,active:true,created_at:new Date("2024-01-15")},
  {user_id:2,email:"bob@example.com",name:"Bob Martin",age:25,active:true,created_at:new Date("2024-02-20")},
  {user_id:3,email:"charlie@example.com",name:"Charlie Durand",age:35,active:false,created_at:new Date("2024-03-10")},
  {user_id:4,email:"diana@example.com",name:"Diana Leroy",age:28,active:true,created_at:new Date("2024-04-05")},
  {user_id:5,email:"eve@example.com",name:"Eve Bernard",age:32,active:false,created_at:new Date("2024-05-12")}
]);
print('✅ users_flat: 5 docs');

print('📦 Seeding orders_nested...');
db.orders_nested.insertMany([
  {order_id:"ORD-001",customer:{id:1,name:"Alice Dupont",email:"alice@example.com",address:{city:"Paris",zip:"75001"}},items:[{product_id:"P001",name:"Laptop",quantity:1,unit_price:999.99}],total:1059.97,status:"completed"},
  {order_id:"ORD-002",customer:{id:2,name:"Bob Martin",email:"bob@example.com",address:{city:"Lyon",zip:"69001"}},items:[{product_id:"P003",name:"Keyboard",quantity:1,unit_price:79.99}],total:79.99,status:"pending"},
  {order_id:"ORD-003",customer:{id:3,name:"Charlie Durand",address:{city:"Marseille"}},items:[{product_id:"P001",quantity:2}],total:2659.94,status:"completed"}
]);
print('✅ orders_nested: 3 docs');

print('📦 Seeding products_mixed...');
db.products_mixed.insertMany([
  {product_id:"P001",type:"physical",name:"Laptop Pro 15",price:999.99,stock:50},
  {product_id:"P002",type:"digital",name:"Software",price:49.99},
  {product_id:"P003",type:"physical",name:"Mouse USB",price:29.99,stock:200},
  {product_id:"P004",type:"service",name:"Warranty",price:199.99},
  {product_id:"P005",type:"bundle",name:"Workstation",price:1499.99,stock:10}
]);
print('✅ products_mixed: 5 docs');

print('📦 Seeding events_evolving...');
db.events_evolving.insertMany([
  {event_id:"E001",event_type:"user_login",user_id:1,timestamp:new Date()},
  {event_id:"E002",event_type:"user_logout",user_id:1,timestamp:new Date()},
  {event_id:"E003",event_type:"user_login",user_id:2,timestamp:new Date(),geolocation:{country:"France",city:"Paris"}},
  {event_id:"E004",event_type:"page_view",user_id:2,timestamp:new Date()},
  {event_id:"E005",event_type:"user_login",user_id:3,timestamp:new Date(),device:{type:"mobile"}},
  {event_id:"E006",event_type:"purchase",user_id:3,timestamp:new Date(),amount:2659.94},
  {event_id:"E007",event_type:"user_login",user_id:4,timestamp:new Date()},
  {event_id:"E008",event_type:"page_view",user_id:4,timestamp:new Date()}
]);
print('✅ events_evolving: 8 docs');

print('📦 Seeding analytics_arrays...');
db.analytics_arrays.insertMany([
  {session_id:"S001",user_id:1,pages_viewed:["/home","/products"],events:[{type:"click"}],metrics:{clicks:5}},
  {session_id:"S002",user_id:2,pages_viewed:["/home"],events:[{type:"click"}],metrics:{clicks:3}},
  {session_id:"S003",user_id:3,pages_viewed:["/home","/cart"],events:[{type:"search"},{type:"payment",amount:2659.94}],metrics:{clicks:12}}
]);
print('✅ analytics_arrays: 3 docs');

print('');
print('✅ COMPLETE: 24 documents loaded in hydra_test_db');