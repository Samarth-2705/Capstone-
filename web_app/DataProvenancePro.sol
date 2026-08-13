// SPDX-License-Identifier: MIT
pragma solidity ^0.8.7;

/**
 * @title DataProvenancePro
 * @notice Upgraded DataProvenance contract for ML pipeline integration
 * @dev Supports RBAC, dataset provenance, ML model versioning,
 *      prediction audit trail, and IPFS CID storage.
 *      Designed for final-year capstone with Ganache / Sepolia compatibility.
 */
contract DataProvenancePro {

    // ─────────────────────────────────────────────
    //  ROLE-BASED ACCESS CONTROL
    // ─────────────────────────────────────────────

    address public owner;

    mapping(address => bool) public isResearcher;
    mapping(address => bool) public isMLSystem;   // off-chain ML backend wallet

    modifier onlyOwner() {
        require(msg.sender == owner, "Not owner");
        _;
    }

    modifier onlyResearcher() {
        require(isResearcher[msg.sender] || msg.sender == owner, "Not a researcher");
        _;
    }

    modifier onlyML() {
        require(isMLSystem[msg.sender] || msg.sender == owner, "Not ML system");
        _;
    }

    // ─────────────────────────────────────────────
    //  DATA STRUCTURES
    // ─────────────────────────────────────────────

    struct Dataset {
        string  dataHash;           // SHA-256 of raw dataset (computed off-chain)
        string  ipfsCID;            // IPFS Content Identifier for full dataset
        address researcher;         // wallet that submitted this record
        uint256 timestamp;          // block.timestamp at submission
        uint256 previousVersion;    // index of previous version (9999 = genesis)
        string  label;              // human-readable name / tag
        bool    active;             // soft-delete / deprecation flag
    }

    struct ModelVersion {
        string  modelHash;          // SHA-256 of serialised model weights
        string  ipfsCID;            // IPFS CID for model weights file
        address submittedBy;        // ML system address
        uint256 timestamp;
        string  algorithmTag;       // e.g. "RandomForest-v2", "LSTM-v1"
        uint256 trainedOnDataset;   // index into datasets[]
        bool    active;
    }

    struct Prediction {
        string  inputHash;          // SHA-256 of input feature vector
        string  outputHash;         // SHA-256 of prediction result JSON
        string  resultCID;          // IPFS CID for full prediction output
        uint256 modelVersionIndex;  // which ModelVersion produced this
        uint256 datasetIndex;       // which Dataset was used for training
        address requestedBy;        // who triggered the inference
        uint256 timestamp;
        bool    verified;           // set true after off-chain verification
    }

    // ─────────────────────────────────────────────
    //  STORAGE ARRAYS
    // ─────────────────────────────────────────────

    Dataset[]       public datasets;
    ModelVersion[]  public modelVersions;
    Prediction[]    public predictions;

    // ─────────────────────────────────────────────
    //  EVENTS  (indexed fields enable fast off-chain filtering)
    // ─────────────────────────────────────────────

    event DatasetStored(
        uint256 indexed index,
        address indexed researcher,
        string  dataHash,
        string  ipfsCID,
        uint256 previousVersion,
        uint256 timestamp
    );

    event ModelVersionStored(
        uint256 indexed index,
        address indexed submittedBy,
        string  modelHash,
        string  algorithmTag,
        uint256 indexed trainedOnDataset,
        uint256 timestamp
    );

    event PredictionStored(
        uint256 indexed index,
        string  inputHash,
        string  outputHash,
        uint256 indexed modelVersionIndex,
        address indexed requestedBy,
        uint256 timestamp
    );

    event PredictionVerified(
        uint256 indexed index,
        address verifiedBy,
        uint256 timestamp
    );

    event ResearcherGranted(address indexed account, address indexed grantedBy);
    event ResearcherRevoked(address indexed account, address indexed revokedBy);
    event MLSystemGranted(address  indexed account, address indexed grantedBy);
    event MLSystemRevoked(address  indexed account, address indexed revokedBy);
    event DatasetDeactivated(uint256 indexed index, address indexed by);
    event ModelDeactivated(uint256 indexed index,   address indexed by);

    // ─────────────────────────────────────────────
    //  CONSTRUCTOR
    // ─────────────────────────────────────────────

    constructor() {
        owner = msg.sender;
        isResearcher[msg.sender] = true; // deployer is researcher by default
    }

    // ─────────────────────────────────────────────
    //  ROLE MANAGEMENT
    // ─────────────────────────────────────────────

    function grantResearcher(address _account) external onlyOwner {
        isResearcher[_account] = true;
        emit ResearcherGranted(_account, msg.sender);
    }

    function revokeResearcher(address _account) external onlyOwner {
        isResearcher[_account] = false;
        emit ResearcherRevoked(_account, msg.sender);
    }

    function grantMLSystem(address _account) external onlyOwner {
        isMLSystem[_account] = true;
        emit MLSystemGranted(_account, msg.sender);
    }

    function revokeMLSystem(address _account) external onlyOwner {
        isMLSystem[_account] = false;
        emit MLSystemRevoked(_account, msg.sender);
    }

    // ─────────────────────────────────────────────
    //  DATASET FUNCTIONS
    // ─────────────────────────────────────────────

    /**
     * @notice Store a dataset hash + IPFS CID on-chain.
     * @param _dataHash    SHA-256 hex digest of the dataset file
     * @param _ipfsCID     IPFS Content Identifier (e.g. "Qm..." or "bafy...")
     * @param _prev        Index of previous dataset version; 9999 = first version
     * @param _label       Human-readable label for this dataset version
     */
    function storeDataset(
        string memory _dataHash,
        string memory _ipfsCID,
        uint256 _prev,
        string memory _label
    ) external onlyResearcher {
        require(bytes(_dataHash).length > 0, "Hash required");
        require(
            _prev == 9999 || _prev < datasets.length,
            "Invalid previous version"
        );

        datasets.push(Dataset({
            dataHash:        _dataHash,
            ipfsCID:         _ipfsCID,
            researcher:      msg.sender,
            timestamp:       block.timestamp,
            previousVersion: _prev,
            label:           _label,
            active:          true
        }));

        uint256 idx = datasets.length - 1;
        emit DatasetStored(idx, msg.sender, _dataHash, _ipfsCID, _prev, block.timestamp);
    }

    function deactivateDataset(uint256 _index) external onlyOwner {
        require(_index < datasets.length, "Index out of range");
        datasets[_index].active = false;
        emit DatasetDeactivated(_index, msg.sender);
    }

    // ─────────────────────────────────────────────
    //  ML MODEL VERSION FUNCTIONS
    // ─────────────────────────────────────────────

    /**
     * @notice Register a trained ML model version.
     * @param _modelHash        SHA-256 of serialised model file (e.g. .pkl, .h5)
     * @param _ipfsCID          IPFS CID for the model weights file
     * @param _algorithmTag     Short tag, e.g. "XGBoost-v3"
     * @param _trainedOnDataset Index of the Dataset used for training
     */
    function storeModelVersion(
        string memory _modelHash,
        string memory _ipfsCID,
        string memory _algorithmTag,
        uint256 _trainedOnDataset
    ) external onlyML {
        require(bytes(_modelHash).length > 0, "Model hash required");
        require(_trainedOnDataset < datasets.length, "Invalid dataset index");
        require(datasets[_trainedOnDataset].active, "Dataset is deactivated");

        modelVersions.push(ModelVersion({
            modelHash:         _modelHash,
            ipfsCID:           _ipfsCID,
            submittedBy:       msg.sender,
            timestamp:         block.timestamp,
            algorithmTag:      _algorithmTag,
            trainedOnDataset:  _trainedOnDataset,
            active:            true
        }));

        uint256 idx = modelVersions.length - 1;
        emit ModelVersionStored(
            idx, msg.sender, _modelHash, _algorithmTag, _trainedOnDataset, block.timestamp
        );
    }

    function deactivateModel(uint256 _index) external onlyOwner {
        require(_index < modelVersions.length, "Index out of range");
        modelVersions[_index].active = false;
        emit ModelDeactivated(_index, msg.sender);
    }

    // ─────────────────────────────────────────────
    //  PREDICTION FUNCTIONS
    // ─────────────────────────────────────────────

    /**
     * @notice Log a prediction made by the ML system.
     * @param _inputHash        SHA-256 of the input feature vector JSON
     * @param _outputHash       SHA-256 of the prediction output JSON
     * @param _resultCID        IPFS CID where full prediction result is stored
     * @param _modelVersionIdx  Index of the ModelVersion used for inference
     * @param _datasetIdx       Index of the Dataset the model was trained on
     */
    function storePrediction(
        string memory _inputHash,
        string memory _outputHash,
        string memory _resultCID,
        uint256 _modelVersionIdx,
        uint256 _datasetIdx
    ) external onlyML {
        require(bytes(_inputHash).length  > 0, "Input hash required");
        require(bytes(_outputHash).length > 0, "Output hash required");
        require(_modelVersionIdx < modelVersions.length, "Invalid model index");
        require(_datasetIdx      < datasets.length,      "Invalid dataset index");
        require(modelVersions[_modelVersionIdx].active,  "Model is deactivated");

        predictions.push(Prediction({
            inputHash:         _inputHash,
            outputHash:        _outputHash,
            resultCID:         _resultCID,
            modelVersionIndex: _modelVersionIdx,
            datasetIndex:      _datasetIdx,
            requestedBy:       msg.sender,
            timestamp:         block.timestamp,
            verified:          false
        }));

        uint256 idx = predictions.length - 1;
        emit PredictionStored(idx, _inputHash, _outputHash, _modelVersionIdx, msg.sender, block.timestamp);
    }

    /**
     * @notice Mark a prediction as independently verified.
     *         Verification logic runs off-chain; only the flag is set on-chain.
     */
    function verifyPrediction(uint256 _index) external onlyResearcher {
        require(_index < predictions.length, "Index out of range");
        predictions[_index].verified = true;
        emit PredictionVerified(_index, msg.sender, block.timestamp);
    }

    // ─────────────────────────────────────────────
    //  READ FUNCTIONS
    // ─────────────────────────────────────────────

    function getDataset(uint256 _index) external view returns (Dataset memory) {
        require(_index < datasets.length, "Index out of range");
        return datasets[_index];
    }

    function getModelVersion(uint256 _index) external view returns (ModelVersion memory) {
        require(_index < modelVersions.length, "Index out of range");
        return modelVersions[_index];
    }

    function getPrediction(uint256 _index) external view returns (Prediction memory) {
        require(_index < predictions.length, "Index out of range");
        return predictions[_index];
    }

    function getDatasetCount()      external view returns (uint256) { return datasets.length; }
    function getModelVersionCount() external view returns (uint256) { return modelVersions.length; }
    function getPredictionCount()   external view returns (uint256) { return predictions.length; }

    /**
     * @notice Return full version chain for a dataset index.
     *         Walks the previousVersion links back to genesis.
     */
    function getVersionChain(uint256 _index) external view returns (uint256[] memory) {
        uint256 count = 0;
        uint256 cursor = _index;

        // count chain length first
        while (cursor != 9999) {
            count++;
            cursor = datasets[cursor].previousVersion;
        }

        uint256[] memory chain = new uint256[](count);
        cursor = _index;
        for (uint256 i = 0; i < count; i++) {
            chain[i] = cursor;
            cursor = datasets[cursor].previousVersion;
        }
        return chain;
    }
}
